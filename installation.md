# NEST Installation and Verification

## 1. Install Required Dependencies

Open a terminal and install Python, pip, the virtual-environment package, and Git:

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv git
```

## 2. Clone the NEST Repository

Clone the NEST repository from GitLab:

```bash
git clone https://gitlab.com/nitk-nest/nest.git
```

Move into the NEST directory:

```bash
cd nest
```

## 3. Create a Python Virtual Environment

Create an isolated Python environment inside the NEST directory:

```bash
python3 -m venv .venv
```

This creates the `.venv` directory containing the isolated Python environment.

## 4. Activate the Virtual Environment

Activate the virtual environment:

```bash
source .venv/bin/activate
```

After activation, the terminal should show `(.venv)` at the beginning of the prompt.

Example:

```text
(.venv) sahil@sahil-IdeaPad-3-15IAU7:~/Desktop/wireless-FQPIE-NEST/nest$
```

## 5. Upgrade Python Packaging Tools

Upgrade `pip`, `setuptools`, and `wheel`:

```bash
python -m pip install --upgrade pip setuptools wheel
```

These tools are required for installing and building Python packages correctly.

## 6. Install and Build NEST

Install NEST and its required Python dependencies:

```bash
python -m pip install -e .
```

The `-e` option performs an **editable installation**. This is useful during development because changes made to the NEST source code are immediately available without reinstalling the package.

## 7. Verify That NEST Is Working

Make sure you are inside the NEST directory:

```bash
cd ~/Desktop/wireless-FQPIE-NEST/nest
```

Activate the virtual environment if it is not already active:

```bash
source .venv/bin/activate
```

Run the FQ-PIE example:

```bash
python examples/qdiscs/fq-pie-point-to-point.py
```

If the example requires root privileges, run:

```bash
sudo .venv/bin/python examples/qdiscs/fq-pie-point-to-point.py
```

## 8. Recommended Verification Command

The preferred sequence is:

```bash
cd ~/Desktop/wireless-FQPIE-NEST/nest
source .venv/bin/activate
python examples/qdiscs/fq-pie-point-to-point.py
```

Only use `sudo` if the example produces a permission-related error.

## Installation Workflow

The complete installation flow is:

```text
Install Python/Git
       ↓
Clone NEST repository
       ↓
Create .venv
       ↓
Activate .venv
       ↓
Upgrade pip/setuptools/wheel
       ↓
Install NEST with pip
       ↓
Run FQ-PIE example
       ↓
Verify NEST is working
       ↓
Run custom FQ-PIE experiments
```

Once the example runs successfully, the NEST installation is ready for the custom FQ-PIE experiments.
