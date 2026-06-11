# Pharmacy Sort — Record, Train, Deploy

Single pill bottle pick-and-place using ACT imitation learning via the Rosetta pipeline.

**Pipeline overview:**
```
DEFINE contract → RECORD demos (lab machine) → CONVERT bags → TRAIN policy (GPU laptop) → DEPLOY (lab machine)
```

---

## Part 1 — Record Demos on the Lab Machine

All commands below run inside the Docker container on the lab machine.

### Step 1 — Copy the contract into place

```bash
cp ~/techin517/final_project/soa_pharmacy_contract.yaml \
   ~/techin517/ros2_ws/src/soa_ros2/soa_bringup/rosetta_contracts/soa_pharmacy_contract.yaml
```

### Step 2 — Verify topic names match your running stack

Before recording, confirm the actual topic names:

```bash
# Terminal 1: Launch the teleop stack (forward controller mode)
ros2 launch soa_bringup soa_bringup.launch.py leader:=true controller:=forward cameras:=true

# Terminal 2: Check topics while the stack is running
ros2 topic list | grep -E "joint_states|wrist_cam|overhead_cam|fwd_controller"
```

Expected topics (update contract if yours differ):

| What | Expected topic |
|---|---|
| Joint states | `/follower/joint_states` |
| Wrist camera | `/follower/wrist_cam/image_raw/compressed` |
| Overhead RealSense | `/static_camera/overhead_cam/color/image_raw/compressed` |
| Arm commands | `/follower/arm_fwd_controller/commands` |
| Gripper commands | `/follower/gripper_fwd_controller/commands` |

If any topic name is different, edit `soa_pharmacy_contract.yaml` before proceeding.

### Step 3 — Launch the episode recorder

In a new terminal (keep the teleop stack running):

```bash
ros2 launch rosetta episode_recorder_launch.py \
    contract_path:=~/techin517/ros2_ws/src/soa_ros2/soa_bringup/rosetta_contracts/soa_pharmacy_contract.yaml \
    bag_base_dir:=~/techin517/huggingface/pharmacy_sort_bags
```

### Step 4 — Record one test episode first

Place the pill bottle at your taped start position. Then trigger recording:

```bash
ros2 action send_goal /episode_recorder/record_episode \
    rosetta_interfaces/action/RecordEpisode \
    "{prompt: 'pick up orange pill bottle and place in box'}"
```

The goal starts immediately. Teleop the arm through the full pick-and-place while it records.
Press Ctrl+C on the action goal (or let it time out at 30s) to stop.

Check the bag was saved:
```bash
ls ~/techin517/huggingface/pharmacy_sort_bags/
```

### Step 5 — Record 25 clean episodes

For each episode:
1. Reset the pill bottle to its taped start position
2. Reset the arm to home pose
3. Trigger a new `record_episode` action (Step 4)
4. Teleop a clean, smooth pick-and-place
5. Discard any episode where you fumbled — use the `--delete-last-episode` flag in `lerobot` dataset tools if needed

**Target: 25 episodes.** Quality matters more than quantity for ACT.

### Step 6 — Convert bags to LeRobot dataset

After recording all episodes:

```bash
python3 ~/techin517/ros2_ws/src/rosetta/rosetta/port_bags.py \
    --raw-dir ~/techin517/huggingface/pharmacy_sort_bags \
    --contract ~/techin517/ros2_ws/src/soa_ros2/soa_bringup/rosetta_contracts/soa_pharmacy_contract.yaml \
    --repo-id weiccc14/pharmacy_sort_pill_bottle \
    --push-to-hub
```

This uploads the dataset to your Hugging Face account. You will need to be logged in:

```bash
huggingface-cli login   # paste your HF token when prompted
```

---

## Part 2 — Train ACT Policy on GPU Laptop

Run these commands on your GPU laptop (not the lab machine). Requires lerobot installed via conda.

### Step 1 — Pull the dataset from Hugging Face

lerobot downloads it automatically during training. Just run:

```bash
lerobot-train \
    --dataset.repo_id=weiccc14/pharmacy_sort_pill_bottle \
    --policy.type=act \
    --output_dir=outputs/train/pharmacy_sort_act \
    --policy.device=cuda \
    --wandb.enable=false
```

Training on 25 episodes takes approximately 2–4 hours on a consumer GPU.
Run it overnight.

### Step 2 — Check training output

When done, the trained model is at:
```
outputs/train/pharmacy_sort_act/checkpoints/last/pretrained_model/
```

Upload it to Hugging Face for deployment:
```bash
huggingface-cli upload weiccc14/pharmacy_sort_act \
    outputs/train/pharmacy_sort_act/checkpoints/last/pretrained_model/
```

---

## Part 3 — Deploy on Lab Machine

Back on the lab machine.

### Step 1 — Launch the follower-only stack (no leader needed for inference)

```bash
ros2 launch soa_bringup soa_bringup.launch.py controller:=forward cameras:=true
```

### Step 2 — Launch the Rosetta policy client

```bash
ros2 launch rosetta rosetta_client_launch.py \
    contract_path:=~/techin517/ros2_ws/src/soa_ros2/soa_bringup/rosetta_contracts/soa_pharmacy_contract.yaml \
    pretrained_name_or_path:=weiccc14/pharmacy_sort_act
```

### Step 3 — Run the policy

Place the pill bottle at the taped start position, then:

```bash
ros2 action send_goal /run_policy \
    rosetta_interfaces/action/RunPolicy \
    "{prompt: 'pick up orange pill bottle and place in box'}"
```

Watch the arm. Hit Ctrl+C immediately if it moves dangerously.

---

## Troubleshooting

**Camera topic times out during recording**
The FAQ in lab1.md covers this: record with `--display_data=false` if using the rerun GUI.
With Rosetta's episode_recorder this isn't an issue — it records bag files directly.

**Joint states not in bag**
Run `ros2 topic echo /follower/joint_states` while the stack is live to confirm data is flowing.
If empty, the `joint_state_broadcaster` controller may not be active — check controller spawner logs.

**Port_bags fails with missing topics**
Re-run with `--strict=false` to allow missing optional topics, or fix the contract topic names first.

**arm_fwd_controller not active**
The launch file defaults to `controller:=forward` which activates both fwd controllers.
If you launched without that arg, check: `ros2 control list_controllers`

**Policy runs but arm barely moves**
The unit conversion (`rad2deg`) must match between training and inference.
Confirm the contract used for `port_bags.py` is the same one used for `rosetta_client_launch.py`.

---

## Quick Reference

| Step | Machine | Command shorthand |
|---|---|---|
| Launch teleop | Lab | `ros2 launch soa_bringup soa_bringup.launch.py leader:=true controller:=forward` |
| Start recorder | Lab | `ros2 launch rosetta episode_recorder_launch.py contract_path:=...` |
| Trigger episode | Lab | `ros2 action send_goal /episode_recorder/record_episode ...` |
| Convert bags | Lab | `python3 port_bags.py --raw-dir ... --push-to-hub` |
| Train ACT | GPU laptop | `lerobot-train --dataset.repo_id=weiccc14/pharmacy_sort_pill_bottle ...` |
| Deploy | Lab | `ros2 launch rosetta rosetta_client_launch.py ...` |
| Run policy | Lab | `ros2 action send_goal /run_policy ...` |
