# City Taxi Simulation with Economic Model

This project simulates a taxi company serving residents in a city grid. It models taxi operations, passenger economics, and company finances over time.

## Features

- **Company Economics**: Tracks capital, income, expenses, and asset values
- **Passenger Economics**: Each resident starts with 100 c.u. and earns 150 c.u. daily
- **Satisfaction Metrics**: Tracks waiting time and cancellation rates
- **Strategy Optimization**: Finds optimal fleet size, pricing, and markup
- **Parallel Processing**: Supports multi-core optimization for faster results

## Components

1. `lab1.py` - Main simulation module
2. `strategy_optimizer.py` - Optimizes taxi company strategy
3. `run_optimization.py` - Command-line tool to run optimization

## Running the Simulation

### Visual Simulation

To run the visual simulation server:

```bash
python lab1.py --server
```

Additional parameters:
```bash
python lab1.py --server --width 40 --height 40 --taxis 5 --residents 47 --km_fare 8 --markup 1.2 --capital 150000 --verbose
```

Note: By default, the server runs without detailed logging to improve performance. Add the `--verbose` flag to display detailed logs.

### Command-line Simulation

To run a fixed number of days without visualization:

```bash
python lab1.py --days 30 --taxis 5 --km_fare 8 --markup 1.2
```

### Optimization

To find the optimal strategy:

```bash
python run_optimization.py
```

With custom parameters:
```bash
python run_optimization.py --min_fleet 3 --max_fleet 10 --min_fare 5 --max_fare 15 --min_markup 1.0 --max_markup 2.0 --days 365
```

#### Parallel Optimization

For faster results, use the parallel processing option:

```bash
python run_optimization.py --parallel
```

You can also specify the number of processes to use:

```bash
python run_optimization.py --parallel --processes 4
```

By default, the parallel mode uses half of the available CPU cores. Pay attention to the memory usage of the process (eg., 32GB RAM are not enough for 363 simulations which are run in 12 parallel processes).

## Model Parameters

- **Fleet Size**: Number of taxis in operation
- **Km Fare**: Price charged to passengers per kilometer
- **Deadhead Markup**: Markup factor for dead-head (driving without passengers) distance
- **Initial Capital**: Company's starting capital (default: 150,000 c.u.)

## Economic Factors

- Vehicle purchase price: 15,000 c.u.
- Vehicle resale value: 9,000 c.u.
- Operating cost per km: 2.5 c.u.
- Resident starting balance: 200 c.u.
- Resident daily income: 150 c.u.

## Strategy Optimization

The strategy optimizer runs simulations across parameter ranges:

- Fleet size (e.g., 5-15 taxis)
- Fare per km (e.g., 5-15 c.u.)
- Deadhead markup (e.g., 1.0-2.0)

It finds the strategy that:

1. Maintains the target capital (≥ 150,000 c.u.)
2. Minimizes cancellation rates
3. Maximizes company profit

## Output

The optimization produces:

- Detailed parameter analysis
- Visualizations of results
- Optimal strategy recommendation
