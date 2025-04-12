from mesa import Model, Agent
from mesa.time import RandomActivation
from mesa.space import MultiGrid
from mesa.datacollection import DataCollector
from mesa.visualization.modules import ChartModule, CanvasGrid, TextElement
from mesa.visualization.ModularVisualization import ModularServer
import random
import heapq


def real_time_to_ticks(real_time_in_hours: int, ticks_per_day: int):
    ticks_per_hour = ticks_per_day / 24

    return real_time_in_hours * ticks_per_hour


def calculate_speed_per_tick(kms_per_hour: int, ticks_per_day: int, kms_in_border: int = 1):
    ticks_per_hour = real_time_to_ticks(1, ticks_per_day)
    kms_per_tick = (kms_per_hour * kms_in_border) / ticks_per_hour

    return kms_per_tick


TAXI_SPEED_KMS_PER_HOUR = 120
ticks_per_day = 576

HALF_HOUR_IN_TICKS = round(real_time_to_ticks(0.5, ticks_per_day))
ONE_HOUR_IN_TICKS = round(real_time_to_ticks(1, ticks_per_day))
THREE_HOURS_IN_TICKS = round(real_time_to_ticks(3, ticks_per_day))


class TaxiAgent(Agent):
    """
    States:
    - "idle": available.
    - "to_pickup": en route to pick up a waiting visitor.
    - "to_destination": carrying a visitor.
    """
    def __init__(self, unique_id, model):
        super().__init__(unique_id, model)
        self.state = "idle"
        self.assigned_request = None
        self.rides_conducted = 0
        self.speed = round(calculate_speed_per_tick(TAXI_SPEED_KMS_PER_HOUR, ticks_per_day))


    def move_toward(self, target):
        """
        Moves one cell toward the target using Manhattan movement.
        """
        current_x, current_y = self.pos
        target_x, target_y = target
        new_x, new_y = current_x, current_y

        distance_to_target = abs(current_x - target_x) + abs(current_y - target_y)
        
        if distance_to_target < self.speed:
            self.model.grid.move_agent(self, target)
            return
        
        borders_to_traverse = self.speed

        while borders_to_traverse > 0:
            if new_x < target_x:
                new_x += 1
            elif new_x > target_x:
                new_x -= 1
            if new_y < target_y:
                new_y += 1
            elif new_y > target_y:
                new_y -= 1

            borders_to_traverse -= 1
            new_pos = (new_x, new_y)
            self.model.grid.move_agent(self, new_pos)


    def step(self):
        if self.state == "to_pickup":
            target = self.assigned_request.pos
            if self.pos != target:
                self.move_toward(target)
            else:
                waiting_time = self.model.current_tick - self.assigned_request.request_time
                self.model.total_waiting_time += waiting_time
                self.model.num_rides += 1
                print(f"{self.unique_id} picked up {self.assigned_request.unique_id} after waiting {waiting_time} ticks.")
                self.state = "to_destination"
        elif self.state == "to_destination":
            target = self.assigned_request.destination
            if self.pos != target:
                self.move_toward(target)
            else:
                resident = self.assigned_request
                is_returning_home = resident.destination == resident.home_pos

                if is_returning_home:
                    print(f"{self.unique_id} dropped off {resident.unique_id} at home.")
                    resident.state = "idle"
                else:
                    print(f"{self.unique_id} dropped off {resident.unique_id} at {target}.")
                    resident.state = "visiting"
                    resident.visit_timer = random.randint(HALF_HOUR_IN_TICKS, THREE_HOURS_IN_TICKS)
                    resident.visits_made += 1
                    if resident.destination_host is not None:
                        host = resident.destination_host
                        host.hosting = True
                        host.visits_hosted += 1
                
                self.rides_conducted += 1
                self.assigned_request = None
                self.state = "idle"


class ResidentAgent(Agent):
    """
    States:
    - "idle": at home, not in transit.
    - "waiting": requested a taxi to start a visit.
    - "in_transit": riding in a taxi.
    - "visiting": visiting someone; has a countdown timer.
    - "hosting": hosting a guest.
    """
    def __init__(self, unique_id, model):
        super().__init__(unique_id, model)
        self.state = "idle"
        self.request_time = None
        self.destination = None
        self.destination_host = None
        self.visit_timer = 0
        self.visits_made = 0
        self.visits_hosted = 0
        self.hosting = False
        self.home_pos = None


    def step(self):
        if self.state == "visiting":
            self.visit_timer -= 1
            if self.visit_timer <= 0:
                print(f"{self.unique_id} finished visiting and requests a taxi to return home.")
                self.destination = self.home_pos
                self.state = "waiting"
                self.request_time = self.model.current_tick
                self.model.add_request_to_queue(self)

                if self.destination_host is not None:
                    self.destination_host.hosting = False
                    self.destination_host = None
        elif self.state == "idle" and not self.hosting:
            if self.random.random() < 0.1:
                self.initiate_visit()


    def initiate_visit(self):
        potential_hosts = [
            agent for agent in self.model.schedule.agents 
            if isinstance(agent, ResidentAgent) and agent.unique_id != self.unique_id and not agent.hosting and agent.state == "idle"
        ]
        if potential_hosts:
            host = self.random.choice(potential_hosts)
            self.destination_host = host
            self.destination = host.pos
            self.request_time = self.model.current_tick
            self.state = "waiting"
            self.model.add_request_to_queue(self)
            print(f"{self.unique_id} at {self.pos} requests a taxi to visit {host.unique_id} at {host.pos}.")


class CityModel(Model):
    """
    - MultiGrid with each cell as a block.
    - Residents placed on unique cells.
    - RandomActivation scheduler.
    - Daily cycle with taxi supply adjustment.
    """
    def __init__(self, width=140, height=170, initial_taxis=50, initial_residents=470, ticks_per_day=100, seed=None):
        super().__init__(seed=seed)
        self.width = width
        self.height = height
        self.initial_taxis = initial_taxis
        self.initial_residents = initial_residents
        self.ticks_per_day = ticks_per_day

        self.grid = MultiGrid(width=self.width, height=self.height, torus=False)
        self.schedule = RandomActivation(self)
        self.request_priority_queue = []

        self.total_waiting_time = 0
        self.num_rides = 0

        self.current_tick = 0
        self.day = 1

        self.extra_taxis = []

        self.datacollector = DataCollector(
            model_reporters={
                "Average Waiting Time": lambda m: m.total_waiting_time / m.num_rides if m.num_rides > 0 else 0,
                "Total Rides": lambda m: m.num_rides,
                "Current Taxis": lambda m: sum(1 for a in m.schedule.agents if isinstance(a, TaxiAgent))
            }
        )

        self._create_taxis()
        self._create_residents()


    def add_request_to_queue(self, resident):
        request_time = resident.request_time
        
        priority_boost = 5 if resident.visits_made < 2 else 0
        priority = request_time - priority_boost

        unique_id = int(resident.unique_id.split('-')[1])
        heapq.heappush(self.request_priority_queue, (priority, request_time, resident.visits_made, unique_id, resident))
        
        print(f"Added request from {resident.unique_id} with priority {priority} (visits: {resident.visits_made})")


    def _create_taxis(self):
        for i in range(self.initial_taxis):
            taxi = TaxiAgent(unique_id=f"Taxi-{i}", model=self)
            x = self.random.randrange(self.width)
            y = self.random.randrange(self.height)
            self.grid.place_agent(taxi, (x, y))
            self.schedule.add(taxi)


    def _create_residents(self):
        for i in range(self.initial_residents):
            resident = ResidentAgent(unique_id=f"Resident-{i}", model=self)
            placed = False
            while not placed:
                x = self.random.randrange(self.width)
                y = self.random.randrange(self.height)
                cell_agents = self.grid.get_cell_list_contents((x, y))
                if not any(isinstance(agent, ResidentAgent) for agent in cell_agents):
                    self.grid.place_agent(resident, (x, y))
                    self.schedule.add(resident)
                    placed = True
                    resident.home_pos = (x, y)


    def dispatch_taxis(self):
        available_taxis = [agent for agent in self.schedule.agents 
                         if isinstance(agent, TaxiAgent) and agent.state == "idle"]
        
        if not available_taxis:
            return
              
        while self.request_priority_queue and available_taxis:
            priority, request_time, visits_made, unique_id, resident = heapq.heappop(self.request_priority_queue)
            
            if resident.state != "waiting":
                continue
                  
            nearest_taxi = self.find_nearest_taxi(resident)
            if nearest_taxi:
                nearest_taxi.assigned_request = resident
                nearest_taxi.state = "to_pickup"
                resident.state = "in_transit"
                      
                print(f"Dispatcher assigned {nearest_taxi.unique_id} to {resident.unique_id} (visit count: {resident.visits_made}).")
                  
                available_taxis.remove(nearest_taxi)
            else:
                request_time = resident.request_time
                heapq.heappush(self.request_priority_queue, (priority, request_time, visits_made, unique_id, resident))
                break


    def find_nearest_taxi(self, resident):
        resident_pos = resident.pos
        min_distance = float('inf')
        nearest_taxi = None
        for agent in self.schedule.agents:
            if isinstance(agent, TaxiAgent) and agent.state == "idle":
                taxi_pos = agent.pos
                distance = abs(resident_pos[0] - taxi_pos[0]) + abs(resident_pos[1] - taxi_pos[1])
                if distance < min_distance:
                    min_distance = distance
                    nearest_taxi = agent
        return nearest_taxi


    def adjust_taxi_supply(self):
        if self.num_rides > 0:
            avg_wait = self.total_waiting_time / self.num_rides
            print(f"Day {self.day} average waiting time: {avg_wait:.2f} ticks.")
            
            hour_threshold = ONE_HOUR_IN_TICKS
            
            if avg_wait > hour_threshold:
                scale_factor = min(5, max(1, int(avg_wait / hour_threshold)))
                taxis_to_add = scale_factor * 2

                print(f"High waiting time (scale factor {scale_factor})—adding {taxis_to_add} extra taxis for next day.")
                
                for i in range(taxis_to_add):
                    taxi = TaxiAgent(unique_id=f"ExtraTaxi-{self.day}-{i}", model=self)
                    x = self.random.randrange(self.width)
                    y = self.random.randrange(self.height)
                    self.grid.place_agent(taxi, (x, y))
                    self.schedule.add(taxi)
                    self.extra_taxis.append(taxi)

        self.total_waiting_time = 0
        self.num_rides = 0


    def step(self):
        self.schedule.step()
        self.dispatch_taxis()
        self.current_tick += 1
        self.datacollector.collect(self)
        if self.current_tick % self.ticks_per_day == 0:
            print(f"\n--- End of Day {self.day} ---")
            self.adjust_taxi_supply()
            self.day += 1


def agent_portrayal(agent):
    portrayal = {"Shape": "circle", "Filled": "true", "r": 0.5}

    if isinstance(agent, TaxiAgent):
        portrayal["Color"] = "yellow"
        portrayal["Layer"] = 1
        if agent.state == "to_pickup":
            portrayal["Color"] = "orange"
        elif agent.state == "to_destination":
            portrayal["Color"] = "green"
    elif isinstance(agent, ResidentAgent):
        portrayal["Color"] = "blue"
        portrayal["Layer"] = 0
        if agent.state == "waiting":
            portrayal["Color"] = "red"
        elif agent.state == "in_transit":
            portrayal["Color"] = "purple"
        elif agent.state == "visiting":
            portrayal["Color"] = "cyan"
        elif agent.hosting:
            portrayal["Color"] = "black"
    
    return portrayal


chart = ChartModule([
    {"Label": "Average Waiting Time", "Color": "Black"},
    {"Label": "Total Rides", "Color": "Blue"},
    {"Label": "Current Taxis", "Color": "Red"}
])


class StatsElement(TextElement):
    def __init__(self):
        pass
    

    def render(self, model):
        avg_wait = model.total_waiting_time / model.num_rides if model.num_rides > 0 else 0
        taxi_count = sum(1 for a in model.schedule.agents if isinstance(a, TaxiAgent))
        resident_count = sum(1 for a in model.schedule.agents if isinstance(a, ResidentAgent))
        waiting_count = len(model.request_priority_queue)
        
        waiting_info = ""
        if model.request_priority_queue:
            queue_copy = model.request_priority_queue.copy()
            waiting_info = "<tr><td colspan='2' style='border: 1px solid black; padding: 8px;'><b>Top 3 Waiting Requests:</b></td></tr>"
            for i in range(min(3, len(queue_copy))):
                if queue_copy:
                    priority, request_time, visits_made, id, resident = heapq.heappop(queue_copy)
                    waiting_info += f"<tr><td style='border: 1px solid black; padding: 8px;'>Request {i+1}</td><td style='border: 1px solid black; padding: 8px; text-align: right;'>{resident.unique_id} (Request time: {request_time}, Visits: {visits_made})</td></tr>"
        
        stats = f"""
        <table style="width:100%; border-collapse: collapse; margin-top: 15px;">
            <tr><th style="border: 1px solid black; padding: 8px; text-align: left;">Statistic</th><th style="border: 1px solid black; padding: 8px; text-align: right;">Value</th></tr>
            <tr><td style="border: 1px solid black; padding: 8px;">Current Day</td><td style="border: 1px solid black; padding: 8px; text-align: right;">{model.day}</td></tr>
            <tr><td style="border: 1px solid black; padding: 8px;">Current Tick</td><td style="border: 1px solid black; padding: 8px; text-align: right;">{model.current_tick}</td></tr>
            <tr><td style="border: 1px solid black; padding: 8px;">Average Waiting Time</td><td style="border: 1px solid black; padding: 8px; text-align: right;">{avg_wait:.2f}</td></tr>
            <tr><td style="border: 1px solid black; padding: 8px;">Total Rides</td><td style="border: 1px solid black; padding: 8px; text-align: right;">{model.num_rides}</td></tr>
            <tr><td style="border: 1px solid black; padding: 8px;">Active Taxis</td><td style="border: 1px solid black; padding: 8px; text-align: right;">{taxi_count}</td></tr>
            <tr><td style="border: 1px solid black; padding: 8px;">Residents</td><td style="border: 1px solid black; padding: 8px; text-align: right;">{resident_count}</td></tr>
            <tr><td style="border: 1px solid black; padding: 8px;">Waiting Requests</td><td style="border: 1px solid black; padding: 8px; text-align: right;">{waiting_count}</td></tr>
            {waiting_info}
        </table>
        """
        return stats


stats_element = StatsElement()

width = 40
height = 40
initial_taxis = 5
initial_residents = 47

grid = CanvasGrid(agent_portrayal, width, height, 400, 400)

server = ModularServer(
    CityModel,
    [grid, stats_element, chart],
    "City Taxi Simulation",
    {"width": width, "height": height, "initial_taxis": initial_taxis, "initial_residents": initial_residents, "ticks_per_day": ticks_per_day}
)
server.port = 8521


if __name__ == "__main__":
    # model = CityModel(width=width, height=height, initial_taxis=initial_taxis, initial_residents=initial_residents, ticks_per_day=ticks_per_day)
    # for i in range(40):
    #     model.step()

    server.launch()
