from mesa import Model, Agent
from mesa.time import RandomActivation
from mesa.space import MultiGrid
from mesa.datacollection import DataCollector
from mesa.visualization.modules import ChartModule
from mesa.visualization.ModularVisualization import ModularServer
import random

class TaxiAgent(Agent):
    """
    Taxi agent assigned by a dispatcher.
    
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

    def move_toward(self, target):
        """
        Moves one cell toward the target using Manhattan movement.
        """
        current_x, current_y = self.pos
        target_x, target_y = target
        new_x, new_y = current_x, current_y
        if current_x < target_x:
            new_x += 1
        elif current_x > target_x:
            new_x -= 1
        if current_y < target_y:
            new_y += 1
        elif current_y > target_y:
            new_y -= 1
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
                print(f"{self.unique_id} dropped off {self.assigned_request.unique_id} at {target}.")
                resident = self.assigned_request
                resident.state = "visiting"
                resident.visit_timer = random.randint(30, 180)
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
    Resident agent that may initiate a visit or host a guest.
    
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

    def step(self):
        if self.state == "visiting":
            self.visit_timer -= 1
            if self.visit_timer <= 0:
                print(f"{self.unique_id} finished visiting and returns home.")
                self.state = "idle"
                if self.destination_host is not None:
                    self.destination_host.hosting = False
                    self.destination_host = None
                self.destination = None
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
            self.model.waiting_requests.append(self)
            print(f"{self.unique_id} at {self.pos} requests a taxi to visit {host.unique_id} at {host.pos}.")

class CityModel(Model):
    """
    A MESA model for a city where residents visit each other and taxis are dispatched.
    
    Features:
    - MultiGrid with each cell as a block.
    - Residents placed on unique cells.
    - RandomActivation scheduler.
    - Data collection and visualization with ChartModule.
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
        self.waiting_requests = []

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

    def dispatch_taxis(self):
        for resident in self.waiting_requests[:]:
            if resident.state != "waiting":
                self.waiting_requests.remove(resident)
                continue
            taxi = self.find_nearest_taxi(resident)
            if taxi:
                taxi.assigned_request = resident
                taxi.state = "to_pickup"
                resident.state = "in_transit"
                self.waiting_requests.remove(resident)
                print(f"Dispatcher assigned {taxi.unique_id} to {resident.unique_id}.")

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
            if avg_wait > 60:
                print("High waiting time—adding extra taxis for next day.")
                for i in range(2):
                    taxi = TaxiAgent(unique_id=f"ExtraTaxi-{self.day}-{i}", model=self)
                    x = self.random.randrange(self.width)
                    y = self.random.randrange(self.height)
                    self.grid.place_agent(taxi, (x, y))
                    self.schedule.add(taxi)
                    self.extra_taxis.append(taxi)
        if self.extra_taxis:
            print("Removing extra taxis from previous day.")
            for taxi in self.extra_taxis:
                self.schedule.remove(taxi)
                self.grid.remove_agent(taxi)
            self.extra_taxis = []
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

chart = ChartModule([
    {"Label": "Average Waiting Time", "Color": "Black"},
    {"Label": "Total Rides", "Color": "Blue"},
    {"Label": "Current Taxis", "Color": "Red"}
])

server = ModularServer(
    CityModel,
    [chart],
    "City Taxi Simulation",
    {"width": 20, "height": 20, "initial_taxis": 5, "initial_residents": 10, "ticks_per_day": 20}
)
server.port = 8521

if __name__ == "__main__":
    # model = CityModel(width=20, height=20, initial_taxis=5, initial_residents=10, ticks_per_day=20)
    # for i in range(40):
    #     model.step()

    server.launch()
