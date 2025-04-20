import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from lab1 import CityModel
import itertools
import statistics


class StrategyOptimizer:
    def __init__(self, width=40, height=40, residents=47, ticks_per_day=576, 
                 fleet_size_range=(2, 10), fare_range=(5, 15), markup_range=(1.0, 2.0),
                 runtime_days=730):  # 2 years (730 days)
        
        self.width = width
        self.height = height
        self.residents = residents
        self.ticks_per_day = ticks_per_day
        self.runtime_days = runtime_days
        
        # Strategy parameter ranges
        self.fleet_size_range = fleet_size_range
        self.fare_range = fare_range
        self.markup_range = markup_range
        
        # Results storage
        self.results = []
        
    
    def parameter_sweep(self, fleet_step=1, fare_step=0.5, markup_step=0.1):
        """Run simulations for all parameter combinations"""
        fleet_sizes = range(self.fleet_size_range[0], self.fleet_size_range[1] + 1, fleet_step)
        
        # Use numpy for fare range to support float steps
        fare_values = []
        current_fare = self.fare_range[0]
        while current_fare <= self.fare_range[1]:
            fare_values.append(current_fare)
            current_fare += fare_step
            
        # Use numpy for markup range to support float steps    
        markup_values = []
        current_markup = self.markup_range[0]
        while current_markup <= self.markup_range[1]:
            markup_values.append(current_markup)
            current_markup += markup_step
        
        total_combinations = len(fleet_sizes) * len(fare_values) * len(markup_values)
        print(f"Running parameter sweep with {total_combinations} combinations...")
        
        for i, (fleet_size, fare, markup) in enumerate(itertools.product(fleet_sizes, fare_values, markup_values)):
            print(f"Running simulation {i+1}/{total_combinations}: "
                  f"Fleet={fleet_size}, Fare={fare:.2f}, Markup={markup:.2f}")
            
            # Run simulation with these parameters
            result = self.run_simulation(fleet_size, fare, markup)
            self.results.append(result)
            
            print(f"Result: Final capital={result['final_capital']:.2f}, "
                  f"Cancellation rate={result['cancellation_rate']:.2%}, "
                  f"Mean satisfaction={result['mean_satisfaction']:.2f}, "
                  f"Median satisfaction={result['median_satisfaction']:.2f}, "
                  f"Mode satisfaction={result['mode_satisfaction']:.2f}")
        
        return self.results
    
    
    def run_simulation(self, fleet_size, fare, markup):
        """Run a single simulation with the given parameters"""
        model = CityModel(
            width=self.width,
            height=self.height,
            initial_taxis=fleet_size,
            initial_residents=self.residents,
            ticks_per_day=self.ticks_per_day,
            km_fare=fare,
            deadhead_markup=markup,
            company_capital=150000,  # Fixed starting capital
            verbose=False  # Turn off verbose output during optimization
        )
        
        # Run for 2 years (730 days)
        for _ in range(self.runtime_days):
            for _ in range(model.ticks_per_day):
                model.step()
                
                # Early stopping if company goes bankrupt
                if model.company_capital < 0:
                    break
        
        # Collect final metrics
        satisfaction_values = [agent.satisfaction_metric for agent in model.schedule.agents 
                              if hasattr(agent, 'satisfaction_metric') and agent.satisfaction_metric > 0]
        
        return {
            'fleet_size': fleet_size,
            'fare': fare,
            'markup': markup,
            'final_capital': model.calculate_total_assets(),
            'company_capital': model.company_capital,
            'total_income': model.total_income,
            'total_expenses': model.total_expenses,
            'cancellation_rate': model.get_cancellation_rate(),
            'mean_satisfaction': statistics.mean(satisfaction_values) if satisfaction_values else 0,
            'median_satisfaction': statistics.median(satisfaction_values) if satisfaction_values else 0,
            'mode_satisfaction': statistics.mode(satisfaction_values) if satisfaction_values else 0
        }
    
    
    def filter_viable_strategies(self, min_capital=150000, max_cancellation=0.2):
        """Filter for strategies that meet target capital and cancellation requirements"""
        viable_strategies = [result for result in self.results 
                            if result['final_capital'] >= min_capital 
                            and result['cancellation_rate'] <= max_cancellation]
        
        return sorted(viable_strategies, key=lambda x: x['final_capital'], reverse=True)
    
    
    def get_optimal_strategy(self, min_capital=150000, max_cancellation=0.2):
        """Get the optimal strategy based on criteria"""
        viable_strategies = self.filter_viable_strategies(min_capital, max_cancellation)
        
        if not viable_strategies:
            print("No viable strategies found!")
            if self.results:
                return max(self.results, key=lambda x: x['final_capital'])
            return None
        
        # Get strategy with highest capital that meets criteria
        optimal_strategy = viable_strategies[0]
        
        print("\nOptimal Strategy:")
        print(f"Fleet Size: {optimal_strategy['fleet_size']}")
        print(f"Fare per km: {optimal_strategy['fare']} c.u.")
        print(f"Deadhead Markup: {optimal_strategy['markup']:.1f}")
        print(f"Final Capital: {optimal_strategy['final_capital']:.2f} c.u.")
        print(f"Cancellation Rate: {optimal_strategy['cancellation_rate']:.2%}")
        print(f"Mean Satisfaction: {optimal_strategy['mean_satisfaction']:.2f}")
        print(f"Median Satisfaction: {optimal_strategy['median_satisfaction']:.2f}")
        print(f"Mode Satisfaction: {optimal_strategy['mode_satisfaction']:.2f}")
        
        return optimal_strategy
    
    
    def visualize_results(self):
        """Create visualizations of the results"""
        if not self.results:
            print("No results to visualize!")
            return
        
        # Convert results to DataFrame for easier analysis
        df = pd.DataFrame(self.results)
        
        # Plot capital vs fleet size and fare
        plt.figure(figsize=(15, 10))
        
        # Capital vs Fleet Size
        plt.subplot(2, 2, 1)
        for fare in sorted(df['fare'].unique()):
            subset = df[df['fare'] == fare]
            plt.plot(subset['fleet_size'], subset['final_capital'], marker='o', label=f'Fare={fare}')
        plt.axhline(y=150000, color='r', linestyle='--', label='Target Capital')
        plt.xlabel('Fleet Size')
        plt.ylabel('Final Capital (c.u.)')
        plt.title('Final Capital vs Fleet Size')
        plt.legend()
        plt.grid(True)
        
        # Capital vs Fare
        plt.subplot(2, 2, 2)
        for fleet in sorted(df['fleet_size'].unique()):
            subset = df[df['fleet_size'] == fleet]
            plt.plot(subset['fare'], subset['final_capital'], marker='o', label=f'Fleet={fleet}')
        plt.axhline(y=150000, color='r', linestyle='--', label='Target Capital')
        plt.xlabel('Fare per km')
        plt.ylabel('Final Capital (c.u.)')
        plt.title('Final Capital vs Fare')
        plt.legend()
        plt.grid(True)
        
        # Cancellation Rate vs Fleet Size
        plt.subplot(2, 2, 3)
        for fare in sorted(df['fare'].unique()):
            subset = df[df['fare'] == fare]
            plt.plot(subset['fleet_size'], subset['cancellation_rate'], marker='o', label=f'Fare={fare}')
        plt.xlabel('Fleet Size')
        plt.ylabel('Cancellation Rate')
        plt.title('Cancellation Rate vs Fleet Size')
        plt.legend()
        plt.grid(True)
        
        # Satisfaction vs Fleet Size
        plt.subplot(2, 2, 4)
        for fare in sorted(df['fare'].unique()):
            subset = df[df['fare'] == fare]
            plt.plot(subset['fleet_size'], subset['mean_satisfaction'], marker='o', label=f'Fare={fare}')
        plt.xlabel('Fleet Size')
        plt.ylabel('Mean Satisfaction (H)')
        plt.title('Mean Satisfaction vs Fleet Size')
        plt.legend()
        plt.grid(True)
        
        plt.tight_layout()
        plt.savefig('strategy_analysis.png')
        plt.show()
        
        # Get optimal strategy and plot its satisfaction histogram
        optimal = self.get_optimal_strategy()
        if optimal:
            print(f"Strategy analysis saved to strategy_analysis.png")


if __name__ == "__main__":
    # Example usage
    optimizer = StrategyOptimizer(
        width=40,
        height=40,
        residents=47,
        ticks_per_day=576,  # Use lower value for faster testing
        fleet_size_range=(5, 15),
        fare_range=(5, 15),
        markup_range=(1.0, 2.0),
    )
    
    # Run a small parameter sweep for testing
    optimizer.parameter_sweep(fleet_step=1, fare_step=0.5, markup_step=0.5)
    
    # Find and display optimal strategy
    optimal = optimizer.get_optimal_strategy()
    
    # Visualize results
    optimizer.visualize_results() 