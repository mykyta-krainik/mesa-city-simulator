# City Taxi Simulation

A Mesa-based agent simulation modeling a taxi dispatch system in a city environment.

## Overview

This simulation models the interactions between taxis and residents in a city grid. Residents request taxi rides to visit other residents, and taxis are dispatched to fulfill these requests based on proximity and priority.

## Features

- Dynamic taxi dispatch system with priority queue
- Residents that visit other residents and return home
- Automatic taxi supply adjustment based on waiting times
- Data collection and visualization of key metrics

## Agents

### Taxi Agent

- States: idle, to_pickup, to_destination
- Moves toward pickup locations and destinations
- Tracks rides conducted

### Resident Agent

- States: idle, waiting, in_transit, visiting, hosting
- Makes visit requests to other residents
- Tracks visits made and visits hosted

## Model Parameters

- Grid size (width × height)
- Initial number of taxis
- Initial number of residents
- Ticks per day (time scale)
- Taxi speed (120 km/h by default)

## Visualization

The simulation includes:
- Grid display showing agent positions and states
- Chart for tracking metrics (waiting time, total rides, number of taxis)
- Statistics panel showing current simulation state

## Running the Simulation

To run the simulation:

```python
python lab1.py
```

This will launch a web server on port 8521. Open a browser and navigate to <http://localhost:8521> to view the simulation.

## Requirements

- Mesa 3.0.3
- Python 3.x (3.12.5 in our case)