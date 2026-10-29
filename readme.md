# PsychoPy SART with EyeLink and Pupillometry

A work-in-progress Sustained Attention to Response Task (SART) built in PsychoPy, with EyeLink 1000 recording, thought probes, and pre/post pupillometry resting periods.

Participants respond to Go stimuli with the spacebar and withhold their response to the No-Go stimulus. A CSV file defines the practice and experimental blocks, stimulus order, and Go/No-Go conditions.

## Setup

Use PsychoPy with the `psychopy-eyelink` package installed.
For eye tracking, connect the PsychoPy computer to the EyeLink Host over Ethernet.
The script expects the Host at `100.1.1.1`.

Keep the script and stimulus file arranged like this:

```text
SART/
├── SART_EyeLink_Reviewed.py
└── CSV/
    └── SART_Stimuli(Stimuli).csv
```

Open the script in PsychoPy Coder. Near the top of the file, set:

```python
dumb = True   # Offline testing; no real eye data
# or
dumb = False  # Use the EyeLink tracker
```

Run the script, enter a participant ID, and choose a fresh EDF filename using 1–8 letters, digits, or underscores.

## Session sequence

1. EyeLink calibration and validation, followed by operator acceptance.
2. Pre-task resting state: instructions, then three minutes fixating on a central dot.
3. SART instructions and practice trials, with feedback and thought probes.
4. Experimental trials, thought probes after selected blocks, and breaks between blocks.
5. Post-task resting state: another three minutes fixating on a central dot.
6. Recording stops and the EDF transfers to the PsychoPy computer.

Calibration uses a **nine-point grid (HV9)**.
The eye(s) recorded are selected on the Host.
The script requests **1000 Hz** sampling; confirm the actual rate on the Host or in the EDF metadata.
Calibration/validation and EDF creation are skipped in dummy mode.

## Controls

- **b:** Begin or continue instructions.
- **Space:** Respond to a SART number.
- **1–5:** Answer a thought probe.
- **c:** Open or repeat EyeLink setup when prompted.
- **v:** Confirm acceptable validation results when prompted.
- **Escape:** Abort the task and run cleanup.

## Trial settings

The stimulus CSV requires these columns:

```text
Order, Type, Block, Trial, Stimuli, Go/No-Go
```

Use `Practice` or `Experiment` for `Type`. Keep each block together, with practice before experimental trials. Legacy `RestingState` rows are ignored because resting periods are scheduled by the script.

The number is displayed for up to **700 ms**; a response ends its display early. A **3-second fixation mask** follows. Responses during the mask are not scored. Practice feedback lasts **700 ms**, and experimental breaks last **30 seconds**. These settings, font sizes, and probe-block selection can be adjusted near the top of the script.

## Output

Each run creates a unique folder under `results/` beside the script, containing:

- **`.EDF`:** Gaze and pupil data, eye-movement events, and task markers. Real recording runs continuously across instructions, trials, probes, breaks, and resting periods.
- **`SART_<participant>.txt`:** Trial responses, accuracy, reaction times, and timing summaries.
- **`SART_<participant>_probes.txt`:** Thought-probe responses and reaction times.
- **`resting_state_summary.tsv`:** Pre/post resting durations and completion status.
- **`session_info.json`:** Session settings and outcome.

EDF markers identify trials, stimulus onsets, responses, probes, and pre/post resting periods.
Open EDF files in EyeLink Data Viewer or convert them with EDF2ASC.
If cleanup reports a failure, check `EDF_recovery.txt` and preserve the original EDF on the Host.

Completed behavioral trials are saved on an orderly abort, including completed trials within the interrupted block.
Force-closing PsychoPy or losing power can prevent saving.


