import numpy as np
import matplotlib.pyplot as plt

# Define the keys and corresponding y-axis titles
KEYS = ["cwnd", "rtt", "dev_rtt", "ssthresh", "rto", "delivery_rate", "pacing_rate"]
KEYS1 = ["bytes", "packets", "drops", "overlimits", "requeues", "backlog", "qlen", 
         "count", "lastcount", "ldelay", "drop_next", "maxpacket", "drop_overlimit"]
EXTRA_FILES = ["netperf_sender", "netperf_receiver", "ping"]
LINK = ["link_utilization"]

# Combine all keys
ALL_KEYS = KEYS + KEYS1 + EXTRA_FILES + LINK

# Y-axis titles mapping
Y_AXIS_TITLES = {
    "netperf_sender": "Sending Rate (Mbps)",
    "netperf_receiver": "Throughput (Mbps)",
    "ping": "Ping Latency (ms)",
    "cwnd": "Congestion Window (Packets)",
    "rtt": "RTT (ms)",
    "dev_rtt": "Deviation RTT (ms)",
    "rto": "Retransmission Timeout (ms)",
    "delivery_rate": "Delivery Rate (Mbps)",
    "pacing_rate": "Pacing Rate (Mbps)",
    "bytes": "Bytes (Bytes)",
    "packets": "Packets (Count)",
    "drops": "Drops (Count)",
    "overlimits": "Overlimits (Count)",
    "requeues": "Requeues (Count)",
    "backlog": "Backlog (Bytes)",
    "qlen": "Queue Length (Packets)",
    "count": "Packet Drop Count",
    "lastcount": "Last Count (Events)",
    "ldelay": "Queue Delay (ms)",
    "drop_next": "Drop Next (ms)",
    "maxpacket": "Max Packet Size (Bytes)",
    "drop_overlimit": "Drops Over Limit (Count)",
    "link_utilization": "Link Utilization (%)"
}

def plot_percentiles(key):
    # Generate filenames based on the key
    file2 = f"fq_codelpp_{key}.dat"
    file1 = f"fq_codel_{key}.dat"
    
    try:
        # Load the data from files and extract the second column
        data1 = np.loadtxt(file1, usecols=(1,))
        data2 = np.loadtxt(file2, usecols=(1,))

         # Convert microseconds to milliseconds for 'ldelay'
        if key == "ldelay":
            data1 = data1 / 1000.0
            data2 = data2 / 1000.0
        
        # Calculate percentiles and median
        modified_median = np.median(data2)
        modified_95th = np.percentile(data2, 95)
        modified_99th = np.percentile(data2, 99)

        original_median = np.median(data1)
        original_95th = np.percentile(data1, 95)
        original_99th = np.percentile(data1, 99)

        # Data for plotting
        metrics = ['Median', '95th Percentile', '99th Percentile']
        
        original_values = [original_median, original_95th, original_99th]
        modified_values = [modified_median, modified_95th, modified_99th]

        # Plot configuration
        x = np.arange(len(metrics))  # Label locations
        width = 0.35  # Bar width

        fig, ax = plt.subplots()
        bars1 = ax.bar(x - width/2, original_values, width, label='CoDel', color='red')
        bars2 = ax.bar(x + width/2, modified_values, width, label='CoDel++', color='blue')
        

        # Add labels, title, and custom ticks
        #ax.set_xlabel('Metrics')
        ax.set_ylabel(Y_AXIS_TITLES.get(key, "Values"))  # Dynamically get y-axis title
        ax.set_title(f'Percentile Comparison: {key.capitalize()} (FQ-CoDel vs. FQ-CoDel++)')
        ax.set_xticks(x)
        ax.set_xticklabels(metrics)
        ax.legend()
        if key == "link_utilization":
            ax.legend(loc='upper left')
            ax.set_ylim(bottom=90)
        # Save the plot to a file
        output_filename = f"percentile_{key}_graph.png"
        plt.savefig(output_filename)
        print(f"Plot saved as '{output_filename}'")
        plt.close(fig)  # Close the figure to save memory
    except FileNotFoundError:
        print(f"Files for key '{key}' not found. Skipping.")
    except Exception as e:
        print(f"An error occurred for key '{key}': {e}")

# Generate plots for all keys
for key in ALL_KEYS:
    plot_percentiles(key)
