for scenario_key in ["cold", "hot", "oscillation"]:
    subprocess.run([
        "python3",
        "-m",
        "core.core_11.run.run_core11",
    ], check=True)