import pandas as pd

# Function to process delivery rate and compute instantaneous link utilization
def calculate_instantaneous_utilization(file_path, link_capacity=10, output_file_path=None):
    """
    Calculate the instantaneous link utilization from the given file containing time and bytes transmitted.
    
    Parameters:
    - file_path: str, path to the input file containing time and bytes transmitted
    - link_capacity: int, link capacity in Mbps (default is 10 Mbps)
    - output_file_path: str, path to save the output file with link utilization
    
    Returns:
    - link_utilization_data: DataFrame containing time and link utilization
    """
    # Read the data from the .dat file (assuming space-separated values)
    data = pd.read_csv(file_path, sep=" ", header=None, names=["time", "bytes"])

    # Link capacity in bytes per second (10 Mbps to bytes per second)
    link_capacity_bytes_per_sec = link_capacity * 10**6 / 8

    # Calculate the instantaneous link utilization using the formula
    data["instantaneous_utilization"] = (data["bytes"] / (link_capacity_bytes_per_sec * data["time"])) * 100

    # Create a new DataFrame with the time column and the calculated instantaneous utilization
    link_utilization_data = data[["time", "instantaneous_utilization"]]

    # Save the results to a new .dat file (if output path is provided)
    if output_file_path:
        link_utilization_data.to_csv(output_file_path, sep=" ", header=False, index=False)

    return link_utilization_data

# Paths for original and modified delivery rate .dat files
original_file_path = "/home/deepa/ALL_Traffic/nest/examples/qdiscs/modified_results/original_bytes.dat"
modified_file_path = "/home/deepa/ALL_Traffic/nest/examples/qdiscs/modified_results/modified_bytes.dat"

# Output paths for link utilization .dat files
original_output_file = "/home/deepa/ALL_Traffic/nest/examples/qdiscs/modified_results/original_link_utilization.dat"
modified_output_file = "/home/deepa/ALL_Traffic/nest/examples/qdiscs/modified_results/modified_link_utilization.dat"

# Calculate and save instantaneous link utilization for both original and modified delivery rates
original_link_utilization = calculate_instantaneous_utilization(original_file_path, link_capacity=10, output_file_path=original_output_file)
modified_link_utilization = calculate_instantaneous_utilization(modified_file_path, link_capacity=10, output_file_path=modified_output_file)

# Display the calculated link utilization for verification (first few rows)
print("Original Link Utilization:")
print(original_link_utilization.head())

print("\nModified Link Utilization:")
print(modified_link_utilization.head())
