from mesa import Model, Agent
from mesa.time import RandomActivation
from mesa.space import MultiGrid
from mesa.datacollection import DataCollector
from mesa.visualization.modules import ChartModule, CanvasGrid, TextElement
from mesa.visualization.ModularVisualization import ModularServer
import random
import heapq
import argparse


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
        
        # Track distances for cost calculation
        self.total_distance = 0  # Total distance traveled in km
        self.pickup_distance = 0  # Distance to pickup current passenger


    def move_toward(self, target):
        """
        Moves one cell toward the target using Manhattan movement.
        """
        current_x, current_y = self.pos
        target_x, target_y = target
        new_x, new_y = current_x, current_y

        distance_to_target = abs(current_x - target_x) + abs(current_y - target_y)
        
        # Calculate actual move distance (limited by speed)
        move_distance = min(distance_to_target, self.speed)
        
        # Track the distance for cost calculation
        self.total_distance += move_distance
        
        # Update company expenses for this movement
        movement_cost = move_distance * self.model.cost_per_km
        self.model.company_capital -= movement_cost
        self.model.total_expenses += movement_cost
        
        # If in to_pickup state, track pickup distance separately 
        if self.state == "to_pickup":
            self.pickup_distance += move_distance
        
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
                
                # Resident pays for ride at pickup
                self.assigned_request.pay_for_ride()
                
                # Reset pickup distance counter
                self.pickup_distance = 0
                
                self.model.log(f"{self.unique_id} picked up {self.assigned_request.unique_id} after waiting {waiting_time} ticks.")
                self.state = "to_destination"
        elif self.state == "to_destination":
            target = self.assigned_request.destination
            if self.pos != target:
                self.move_toward(target)
            else:
                resident = self.assigned_request
                is_returning_home = resident.destination == resident.home_pos

                if is_returning_home:
                    self.model.log(f"{self.unique_id} dropped off {resident.unique_id} at home.")
                    resident.state = "idle"
                else:
                    self.model.log(f"{self.unique_id} dropped off {resident.unique_id} at {target}.")
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
        
        # Economic attributes
        self.balance = 200  # Starting money
        self.ride_fare = 0  # Current ride cost
        
        # Satisfaction metrics
        self.satisfaction_metric = 0  # H metric
        self.cancelled_rides = 0


    def step(self):
        if self.state == "visiting":
            self.visit_timer -= 1
            if self.visit_timer <= 0:
                self.model.log(f"{self.unique_id} finished visiting and requests a taxi to return home.")
                self.destination = self.home_pos
                self.state = "waiting"
                self.request_time = self.model.current_tick
                
                # Calculate fare before requesting taxi
                self.calculate_ride_fare()
                
                # Only request taxi if can afford ride
                if self.can_afford_ride():
                    self.model.add_request_to_queue(self)
                else:
                    self.model.log(f"{self.unique_id} cannot afford ride home (cost: {self.ride_fare}, balance: {self.balance})")
                    self.teleport_home()

                if self.destination_host is not None:
                    self.destination_host.hosting = False
                    self.destination_host = None
        elif self.state == "waiting":
            # Check satisfaction metric H
            waiting_time = self.model.current_tick - self.request_time
            self.satisfaction_metric = waiting_time / ONE_HOUR_IN_TICKS
            
            # If H > 1, cancel ride and return home
            if self.satisfaction_metric > 1:
                self.model.log(f"{self.unique_id} cancelled ride due to long wait time (H={self.satisfaction_metric:.2f})")
                self.cancelled_rides += 1
                self.teleport_home()
                
        elif self.state == "idle" and not self.hosting:
            if self.random.random() < 0.1:
                self.initiate_visit()
                
        # Daily income
        if self.model.current_tick % self.model.ticks_per_day == 0:
            self.balance += 50
            self.model.log(f"{self.unique_id} received daily income, new balance: {self.balance}")


    def teleport_home(self):
        """Teleport back home when ride is cancelled"""
        self.model.grid.move_agent(self, self.home_pos)
        self.state = "idle"
        self.satisfaction_metric = 0


    def calculate_ride_fare(self):
        """Calculate the fare for the current ride request"""
        if self.destination is None:
            self.ride_fare = 0
            return
            
        # Calculate distance to destination
        current_x, current_y = self.pos
        dest_x, dest_y = self.destination
        distance = abs(current_x - dest_x) + abs(current_y - dest_y)
        
        # Each cell is treated as 1 km
        self.ride_fare = distance * self.model.km_fare
        self.model.log(f"{self.unique_id} ride fare calculated: {self.ride_fare} c.u. for {distance} km")
        
        # Track for affordability metrics
        self.model.total_ride_requests += 1


    def can_afford_ride(self):
        """Check if resident can afford the calculated fare"""
        can_afford = self.balance >= self.ride_fare
        
        # Track affordability for fare adjustments
        if not can_afford:
            self.model.refused_rides_due_to_cost += 1
            
        return can_afford


    def pay_for_ride(self):
        """Deduct fare from balance when taxi is assigned"""
        if self.ride_fare > 0:
            self.balance -= self.ride_fare
            self.model.total_income += self.ride_fare
            self.model.company_capital += self.ride_fare
            self.model.log(f"{self.unique_id} paid {self.ride_fare} c.u. for ride, new balance: {self.balance}")


    def initiate_visit(self):
        potential_hosts = [
            agent for agent in self.model.schedule.agents 
            if isinstance(agent, ResidentAgent) and agent.unique_id != self.unique_id and not agent.hosting and agent.state == "idle"
        ]
        if potential_hosts:
            host = self.random.choice(potential_hosts)
            self.destination_host = host
            self.destination = host.pos
            
            # Calculate fare before requesting taxi
            self.calculate_ride_fare()
            
            # Only request taxi if can afford ride
            if self.can_afford_ride():
                self.request_time = self.model.current_tick
                self.state = "waiting"
                self.model.add_request_to_queue(self)
                self.model.log(f"{self.unique_id} at {self.pos} requests a taxi to visit {host.unique_id} at {host.pos}. Fare: {self.ride_fare} c.u.")
            else:
                self.model.log(f"{self.unique_id} wants to visit {host.unique_id} but cannot afford ride (cost: {self.ride_fare}, balance: {self.balance})")


class CityModel(Model):
    """
    - MultiGrid with each cell as a block.
    - Residents placed on unique cells.
    - RandomActivation scheduler.
    - Daily cycle with taxi supply adjustment.
    """
    def __init__(self, width=140, height=170, initial_taxis=50, initial_residents=470, ticks_per_day=100, seed=None,
                 km_fare=10, deadhead_markup=1.5, company_capital=150000, verbose=True):
        super().__init__(seed=seed)
        self.width = width
        self.height = height
        self.initial_taxis = initial_taxis
        self.initial_residents = initial_residents
        self.ticks_per_day = ticks_per_day
        
        # Company finances
        self.company_capital = company_capital
        self.initial_capital = company_capital
        self.target_capital = 150000  # Target capital after 2 years
        self.vehicle_purchase_price = 15000
        self.vehicle_resale_value = 9000
        self.cost_per_km = 2.5
        self.base_km_fare = km_fare  # Base price charged to passengers per km
        self.deadhead_markup = deadhead_markup  # Markup for dead-head distance
        self.km_fare = self.calculate_effective_fare(km_fare, deadhead_markup)
        
        # Financial tracking
        self.total_income = 0
        self.total_expenses = 0
        self.taxi_assets_value = 0
        
        # Controls output verbosity
        self.verbose = verbose
        
        self.grid = MultiGrid(width=self.width, height=self.height, torus=False)
        self.schedule = RandomActivation(self)
        self.request_priority_queue = []

        self.total_waiting_time = 0
        self.num_rides = 0

        self.current_tick = 0
        self.day = 1

        self.extra_taxis = []
        
        # Track fare affordability
        self.refused_rides_due_to_cost = 0
        self.total_ride_requests = 0

        self.datacollector = DataCollector(
            model_reporters={
                "Average Waiting Time": lambda m: m.total_waiting_time / m.num_rides if m.num_rides > 0 else 0,
                "Total Rides": lambda m: m.num_rides,
                "Current Taxis": lambda m: sum(1 for a in m.schedule.agents if isinstance(a, TaxiAgent)),
                "Company Capital": lambda m: m.company_capital,
                "Total Assets": lambda m: m.calculate_total_assets(),
                "Total Income": lambda m: m.total_income,
                "Total Expenses": lambda m: m.total_expenses,
                "Cancellation Rate": self.get_cancellation_rate,
                "Average Satisfaction": self.get_average_satisfaction,
                "Current Fare": lambda m: m.km_fare,
                "Affordability Rate": self.get_affordability_rate
            },
            agent_reporters={
                "Balance": lambda a: a.balance if isinstance(a, ResidentAgent) else None,
                "Satisfaction": lambda a: a.satisfaction_metric if isinstance(a, ResidentAgent) else None,
                "Total Distance": lambda a: a.total_distance if isinstance(a, TaxiAgent) else None
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
        
        self.log(f"Added request from {resident.unique_id} with priority {priority} (visits: {resident.visits_made})")


    def _create_taxis(self):
        capital_needed = self.initial_taxis * self.vehicle_purchase_price
        if capital_needed > self.company_capital:
            affordable_taxis = self.company_capital // self.vehicle_purchase_price
            self.initial_taxis = max(1, affordable_taxis - 1)  # Ensure at least one taxi, keep some reserve
            self.log(f"WARNING: Not enough capital for {self.initial_taxis} taxis. Reducing to {affordable_taxis}.")
        
        for i in range(self.initial_taxis):
            taxi = TaxiAgent(unique_id=f"Taxi-{i}", model=self)
            x = self.random.randrange(self.width)
            y = self.random.randrange(self.height)
            self.grid.place_agent(taxi, (x, y))
            self.schedule.add(taxi)
            
            # Deduct purchase price from capital
            self.company_capital -= self.vehicle_purchase_price
            self.total_expenses += self.vehicle_purchase_price
            
            # Add to asset value
            self.taxi_assets_value += self.vehicle_resale_value
            
            self.log(f"Purchased taxi {taxi.unique_id} for {self.vehicle_purchase_price} c.u.")


    def add_taxi(self, taxi_id):
        """Add a new taxi if company can afford it"""
        if self.company_capital >= self.vehicle_purchase_price:
            taxi = TaxiAgent(unique_id=taxi_id, model=self)
            x = self.random.randrange(self.width)
            y = self.random.randrange(self.height)
            self.grid.place_agent(taxi, (x, y))
            self.schedule.add(taxi)
            
            # Deduct purchase price from capital
            self.company_capital -= self.vehicle_purchase_price
            self.total_expenses += self.vehicle_purchase_price
            
            # Add to asset value
            self.taxi_assets_value += self.vehicle_resale_value
            
            self.log(f"Purchased taxi {taxi_id} for {self.vehicle_purchase_price} c.u.")
            return True
        else:
            self.log(f"Cannot afford new taxi. Current capital: {self.company_capital} c.u.")
            return False


    def calculate_total_assets(self):
        """Calculate company's total assets (cash + taxi resale value)"""
        return self.company_capital + self.taxi_assets_value


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
                      
                self.log(f"Dispatcher assigned {nearest_taxi.unique_id} to {resident.unique_id} (visit count: {resident.visits_made}).")
                  
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
        # Calculate current financial status
        total_assets = self.calculate_total_assets()
        self.log(f"Day {self.day} financial status:")
        self.log(f"  Capital: {self.company_capital:.2f} c.u.")
        self.log(f"  Asset value: {self.taxi_assets_value:.2f} c.u.")
        self.log(f"  Total assets: {total_assets:.2f} c.u.")
        self.log(f"  Income: {self.total_income:.2f} c.u.")
        self.log(f"  Expenses: {self.total_expenses:.2f} c.u.")
        
        if self.num_rides > 0:
            avg_wait = self.total_waiting_time / self.num_rides
            self.log(f"Day {self.day} average waiting time: {avg_wait:.2f} ticks.")
            
            # Calculate cancellation rate for the day
            cancelled_rides = sum(resident.cancelled_rides for resident in self.schedule.agents 
                                if isinstance(resident, ResidentAgent))
            total_requests = self.num_rides + cancelled_rides
            cancellation_rate = cancelled_rides / total_requests if total_requests > 0 else 0
            self.log(f"Day {self.day} cancellation rate: {cancellation_rate:.2%}")
            
            # Reset counters for next day
            for resident in self.schedule.agents:
                if isinstance(resident, ResidentAgent):
                    resident.cancelled_rides = 0
            
            hour_threshold = ONE_HOUR_IN_TICKS
            
            # Decide whether to add taxis based on waiting time and financial status
            if avg_wait > hour_threshold and self.company_capital >= self.vehicle_purchase_price * 2:
                scale_factor = min(5, max(1, int(avg_wait / hour_threshold)))
                taxis_to_add = min(scale_factor, self.company_capital // self.vehicle_purchase_price)
                
                if taxis_to_add > 0:
                    self.log(f"High waiting time (scale factor {scale_factor})—adding {taxis_to_add} extra taxis for next day.")
                    
                    for i in range(taxis_to_add):
                        taxi_id = f"ExtraTaxi-{self.day}-{i}"
                        success = self.add_taxi(taxi_id)
                        if success:
                            self.extra_taxis.append(taxi_id)
                        else:
                            break

        self.total_waiting_time = 0
        self.num_rides = 0


    def step(self):
        self.schedule.step()
        self.dispatch_taxis()
        self.current_tick += 1
        self.datacollector.collect(self)

        if self.current_tick % 50 == 0:
            # Recalculate fare at end of day
            self.recalculate_fare()


        if self.current_tick % self.ticks_per_day == 0:
            self.log(f"\n--- End of Day {self.day} ---")
            self.adjust_taxi_supply()
            
            self.day += 1


    def get_cancellation_rate(self):
        """Calculate the overall cancellation rate"""
        total_cancelled = sum(resident.cancelled_rides for resident in self.schedule.agents 
                            if isinstance(resident, ResidentAgent))
        if self.num_rides + total_cancelled == 0:
            return 0
        return total_cancelled / (self.num_rides + total_cancelled)
    
    
    def get_average_satisfaction(self):
        """Calculate the average satisfaction metric for residents"""
        satisfaction_values = [resident.satisfaction_metric for resident in self.schedule.agents 
                              if isinstance(resident, ResidentAgent) and resident.satisfaction_metric > 0]
        if not satisfaction_values:
            return 0
        return sum(satisfaction_values) / len(satisfaction_values)


    def log(self, message):
        """Print message only if verbose mode is enabled"""
        if self.verbose:
            print(message)


    def calculate_effective_fare(self, base_fare, markup):
        """
        Calculate fare that covers operating costs and includes markup for deadhead distance
        """
        # Ensure fare covers at least operating costs
        min_viable_fare = self.cost_per_km * 1.1  # 10% profit margin minimum
        
        # Apply markup to account for deadhead trips
        effective_fare = max(base_fare, min_viable_fare) * (1 + (markup - 1) * 0.5)
        
        # Balance fare based on company capital status
        if self.company_capital < self.initial_capital * 0.5:
            # If company is losing money, increase fare
            effective_fare *= 1.1
        elif self.company_capital > self.initial_capital * 1.5:
            # If company is making too much profit, make rides more affordable
            effective_fare *= 0.95
            
        # Round to 2 decimal places for consistency
        return round(effective_fare, 2)
    
    def recalculate_fare(self):
        """Recalculate fare based on current conditions"""
        # Get affordability metrics
        if self.total_ride_requests > 0:
            affordability_rate = 1 - (self.refused_rides_due_to_cost / self.total_ride_requests)
        else:
            affordability_rate = 1.0
            
        # If many people can't afford rides, decrease fare slightly
        if affordability_rate < 0.8 and self.base_km_fare > self.cost_per_km * 1.2:
            self.base_km_fare = max(self.cost_per_km * 1.2, self.base_km_fare * 0.95)
            self.log(f"Decreasing fare due to low affordability ({affordability_rate:.2%})")
        
        # Recalculate effective fare
        self.km_fare = self.calculate_effective_fare(self.base_km_fare, self.deadhead_markup)
        self.log(f"Recalculated fare: {self.km_fare} c.u./km (base: {self.base_km_fare}, markup: {self.deadhead_markup})")
    
        # Reset counters
        self.refused_rides_due_to_cost = 0
        self.total_ride_requests = 0


    def get_affordability_rate(self):
        """Calculate the rate at which residents can afford rides"""
        if self.total_ride_requests == 0:
            return 1.0
        return 1 - (self.refused_rides_due_to_cost / self.total_ride_requests)


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


class FinancialHeader(TextElement):
    def render(self, model):
        return "<h3>Financial Metrics</h3>"

class RideHeader(TextElement):
    def render(self, model):
        return "<h3>Ride Metrics</h3>"

# Create text headers for chart sections
financial_header = FinancialHeader()
ride_header = RideHeader()

# Create two separate charts - one for financial metrics and one for ride metrics
financial_chart = ChartModule([
    {"Label": "Company Capital", "Color": "Green"},
    {"Label": "Total Assets", "Color": "Purple"},
    {"Label": "Total Income", "Color": "Blue"},
    {"Label": "Total Expenses", "Color": "Red"},
    {"Label": "Current Fare", "Color": "Orange"}
], canvas_height=200, data_collector_name="datacollector")

ride_chart = ChartModule([
    {"Label": "Average Waiting Time", "Color": "Black"},
    {"Label": "Total Rides", "Color": "Blue"},
    {"Label": "Current Taxis", "Color": "Red"},
    {"Label": "Cancellation Rate", "Color": "Orange"},
    {"Label": "Average Satisfaction", "Color": "Brown"},
    {"Label": "Affordability Rate", "Color": "Pink"}
], canvas_height=200, data_collector_name="datacollector")


class StatsElement(TextElement):
    def __init__(self):
        pass
    

    def render(self, model):
        avg_wait = model.total_waiting_time / model.num_rides if model.num_rides > 0 else 0
        taxi_count = sum(1 for a in model.schedule.agents if isinstance(a, TaxiAgent))
        resident_count = sum(1 for a in model.schedule.agents if isinstance(a, ResidentAgent))
        waiting_count = len(model.request_priority_queue)
        
        # Calculate satisfaction statistics
        satisfaction_values = [a.satisfaction_metric for a in model.schedule.agents 
                              if isinstance(a, ResidentAgent) and a.satisfaction_metric > 0]
        avg_satisfaction = sum(satisfaction_values) / len(satisfaction_values) if satisfaction_values else 0
        
        # Calculate cancellation rate
        total_cancelled = sum(a.cancelled_rides for a in model.schedule.agents if isinstance(a, ResidentAgent))
        cancellation_rate = total_cancelled / (model.num_rides + total_cancelled) if (model.num_rides + total_cancelled) > 0 else 0
        
        # Calculate affordability rate
        affordability_rate = model.get_affordability_rate()
        
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
            <tr><th colspan="2" style="border: 1px solid black; padding: 8px; background-color: #f2f2f2; text-align: center;">Simulation Status</th></tr>
            <tr><td style="border: 1px solid black; padding: 8px;">Current Day</td><td style="border: 1px solid black; padding: 8px; text-align: right;">{model.day}</td></tr>
            <tr><td style="border: 1px solid black; padding: 8px;">Current Tick</td><td style="border: 1px solid black; padding: 8px; text-align: right;">{model.current_tick}</td></tr>
            
            <tr><th colspan="2" style="border: 1px solid black; padding: 8px; background-color: #f2f2f2; text-align: center;">Financial Metrics</th></tr>
            <tr><td style="border: 1px solid black; padding: 8px;">Company Capital</td><td style="border: 1px solid black; padding: 8px; text-align: right;">{model.company_capital:.2f} c.u.</td></tr>
            <tr><td style="border: 1px solid black; padding: 8px;">Total Assets</td><td style="border: 1px solid black; padding: 8px; text-align: right;">{model.calculate_total_assets():.2f} c.u.</td></tr>
            <tr><td style="border: 1px solid black; padding: 8px;">Total Income</td><td style="border: 1px solid black; padding: 8px; text-align: right;">{model.total_income:.2f} c.u.</td></tr>
            <tr><td style="border: 1px solid black; padding: 8px;">Total Expenses</td><td style="border: 1px solid black; padding: 8px; text-align: right;">{model.total_expenses:.2f} c.u.</td></tr>
            <tr><td style="border: 1px solid black; padding: 8px;">Current Fare</td><td style="border: 1px solid black; padding: 8px; text-align: right;">{model.km_fare:.2f} c.u./km</td></tr>
            
            <tr><th colspan="2" style="border: 1px solid black; padding: 8px; background-color: #f2f2f2; text-align: center;">Service Metrics</th></tr>
            <tr><td style="border: 1px solid black; padding: 8px;">Average Waiting Time</td><td style="border: 1px solid black; padding: 8px; text-align: right;">{avg_wait:.2f} ticks</td></tr>
            <tr><td style="border: 1px solid black; padding: 8px;">Avg. Satisfaction (H)</td><td style="border: 1px solid black; padding: 8px; text-align: right;">{avg_satisfaction:.2f}</td></tr>
            <tr><td style="border: 1px solid black; padding: 8px;">Cancellation Rate</td><td style="border: 1px solid black; padding: 8px; text-align: right;">{cancellation_rate:.2%}</td></tr>
            <tr><td style="border: 1px solid black; padding: 8px;">Affordability Rate</td><td style="border: 1px solid black; padding: 8px; text-align: right;">{affordability_rate:.2%}</td></tr>
            <tr><td style="border: 1px solid black; padding: 8px;">Total Rides</td><td style="border: 1px solid black; padding: 8px; text-align: right;">{model.num_rides}</td></tr>
            
            <tr><th colspan="2" style="border: 1px solid black; padding: 8px; background-color: #f2f2f2; text-align: center;">Population</th></tr>
            <tr><td style="border: 1px solid black; padding: 8px;">Active Taxis</td><td style="border: 1px solid black; padding: 8px; text-align: right;">{taxi_count}</td></tr>
            <tr><td style="border: 1px solid black; padding: 8px;">Residents</td><td style="border: 1px solid black; padding: 8px; text-align: right;">{resident_count}</td></tr>
            <tr><td style="border: 1px solid black; padding: 8px;">Waiting Requests</td><td style="border: 1px solid black; padding: 8px; text-align: right;">{waiting_count}</td></tr>
            
            {waiting_info}
        </table>
        """
        return stats


stats_element = StatsElement()

pixels_per_cell = 10
width = 40
height = 40
canvas_width = width * pixels_per_cell
canvas_height = height * pixels_per_cell
initial_taxis = 5
initial_residents = 47
km_fare = 5
deadhead_markup = 1.2
company_capital = 150000

grid = CanvasGrid(agent_portrayal, width, height, canvas_width, canvas_height)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Run City Taxi Simulation')
    parser.add_argument('--server', action='store_true', help='Run visualization server')
    parser.add_argument('--width', type=int, default=40, help='Grid width')
    parser.add_argument('--height', type=int, default=40, help='Grid height')
    parser.add_argument('--taxis', type=int, default=5, help='Initial number of taxis')
    parser.add_argument('--residents', type=int, default=47, help='Number of residents')
    parser.add_argument('--ticks_per_day', type=int, default=576, help='Ticks per day')
    parser.add_argument('--km_fare', type=float, default=6, help='Fare per km')
    parser.add_argument('--markup', type=float, default=1.1, help='Deadhead markup')
    parser.add_argument('--capital', type=float, default=150000, help='Initial company capital')
    parser.add_argument('--days', type=int, default=10, help='Number of days to simulate if not running server')
    parser.add_argument('--verbose', action='store_true', help='Print detailed logs')

    args = parser.parse_args()
    
    width = args.width
    height = args.height
    initial_taxis = args.taxis
    initial_residents = args.residents
    
    # Set verbosity - always verbose in CLI mode, optional in server mode
    verbose = True if not args.server else args.verbose
    
    if args.server:
        # Run visualization server
        server = ModularServer(
            CityModel,
            [grid, stats_element, financial_header, financial_chart, ride_header, ride_chart],
            "City Taxi Simulation",
            {
                "width": width, 
                "height": height, 
                "initial_taxis": initial_taxis, 
                "initial_residents": initial_residents, 
                "ticks_per_day": args.ticks_per_day,
                "km_fare": args.km_fare,
                "deadhead_markup": args.markup,
                "company_capital": args.capital,
                "verbose": verbose
            }
        )
        server.port = 8521
        server.launch()
    else:
        # Run model for specified number of days
        print(f"Running simulation for {args.days} days...")
        print(f"Parameters: Taxis={initial_taxis}, Residents={initial_residents}, Fare={args.km_fare}, Markup={args.markup}")
        
        model = CityModel(
            width=width, 
            height=height, 
            initial_taxis=initial_taxis, 
            initial_residents=initial_residents, 
            ticks_per_day=args.ticks_per_day,
            km_fare=args.km_fare,
            deadhead_markup=args.markup,
            company_capital=args.capital,
            verbose=verbose
        )
        
        for day in range(args.days):
            for _ in range(model.ticks_per_day):
                model.step()
                
            # Print daily summary
            total_assets = model.calculate_total_assets()
            waiting_count = len(model.request_priority_queue)
            
            print(f"Day {day+1} summary:")
            print(f"  Capital: {model.company_capital:.2f} c.u.")
            print(f"  Assets: {total_assets:.2f} c.u.")
            print(f"  Waiting requests: {waiting_count}")
            
        # Print final stats
        print("\nFinal statistics:")
        print(f"Company capital: {model.company_capital:.2f} c.u.")
        print(f"Total assets: {model.calculate_total_assets():.2f} c.u.")
        print(f"Total income: {model.total_income:.2f} c.u.")
        print(f"Total expenses: {model.total_expenses:.2f} c.u.")
        
        # Calculate satisfaction statistics
        satisfaction_values = [agent.satisfaction_metric for agent in model.schedule.agents 
                              if isinstance(agent, ResidentAgent) and agent.satisfaction_metric > 0]
        
        if satisfaction_values:
            import statistics
            print(f"Mean satisfaction: {statistics.mean(satisfaction_values):.2f}")
            print(f"Median satisfaction: {statistics.median(satisfaction_values):.2f}")
            try:
                print(f"Mode satisfaction: {statistics.mode(satisfaction_values):.2f}")
            except:
                print("Mode satisfaction: N/A (no unique mode)")
