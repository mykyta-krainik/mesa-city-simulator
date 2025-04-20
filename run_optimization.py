from strategy_optimizer import StrategyOptimizer
import argparse
import time

def main():
    parser = argparse.ArgumentParser(description='Run taxi strategy optimization')
    parser.add_argument('--width', type=int, default=20, help='Grid width')
    parser.add_argument('--height', type=int, default=20, help='Grid height')
    parser.add_argument('--residents', type=int, default=30, help='Number of residents')
    parser.add_argument('--ticks_per_day', type=int, default=576, help='Ticks per day')
    parser.add_argument('--days', type=int, default=730, help='Number of days to simulate (default: 2 years)')
    parser.add_argument('--min_fleet', type=int, default=5, help='Minimum fleet size to test')
    parser.add_argument('--max_fleet', type=int, default=15, help='Maximum fleet size to test')
    parser.add_argument('--min_fare', type=float, default=5, help='Minimum fare per km')
    parser.add_argument('--max_fare', type=float, default=15, help='Maximum fare per km')
    parser.add_argument('--min_markup', type=float, default=1.0, help='Minimum deadhead markup')
    parser.add_argument('--max_markup', type=float, default=2.0, help='Maximum deadhead markup')
    parser.add_argument('--fleet_step', type=int, default=1, help='Step size for fleet size')
    parser.add_argument('--fare_step', type=float, default=0.5, help='Step size for fare')
    parser.add_argument('--markup_step', type=float, default=0.5, help='Step size for markup')
    
    args = parser.parse_args()
    
    print("Taxi Company Strategy Optimizer")
    print("==============================")
    print(f"Grid: {args.width}x{args.height}, Residents: {args.residents}")
    print(f"Simulation period: {args.days} days ({args.days/365:.1f} years)")
    print("Parameter ranges:")
    print(f"  Fleet size: {args.min_fleet}-{args.max_fleet}, step {args.fleet_step}")
    print(f"  Fare: {args.min_fare}-{args.max_fare} c.u., step {args.fare_step}")
    print(f"  Markup: {args.min_markup}-{args.max_markup}, step {args.markup_step}")
    print()
    
    # Create optimizer with args
    optimizer = StrategyOptimizer(
        width=args.width,
        height=args.height,
        residents=args.residents,
        ticks_per_day=args.ticks_per_day,
        fleet_size_range=(args.min_fleet, args.max_fleet),
        fare_range=(args.min_fare, args.max_fare),
        markup_range=(args.min_markup, args.max_markup),
        runtime_days=args.days
    )
    
    # Start timer
    start_time = time.time()
    
    # Run parameter sweep
    optimizer.parameter_sweep(
        fleet_step=args.fleet_step,
        fare_step=args.fare_step,
        markup_step=args.markup_step
    )
    
    # Find optimal strategy
    optimal = optimizer.get_optimal_strategy()
    
    # Visualize results
    optimizer.visualize_results()
    
    # Print runtime
    elapsed_time = time.time() - start_time
    print(f"\nOptimization completed in {elapsed_time/60:.1f} minutes")


if __name__ == "__main__":
    main() 