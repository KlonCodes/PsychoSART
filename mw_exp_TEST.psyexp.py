"""
:::Colin Note:::
    This is a test version to play around with optimizations.
    may break.
"""

import csv, time, pylink, os, platform, json
from pathlib import Path
from datetime import datetime
from EyeLinkCoreGraphicsPsychoPy import EyeLinkCoreGraphicsPsychoPy
from psychopy import visual, core, event, gui
from string import ascii_letters, digits

# ----------------------------
# Adjustable task settings
# ----------------------------
dumb = True                   # Run in dummy mode (no real eye-tracking data)
full_screen = True            # Run the Task in full-screen mode
sartDark = "#202020"          # Background colour
sartLight = "#acacac"         # Text colour
# Sizes are fractions of window height, independent of monitor calibration.
# At 1080 pixels tall these are approximately 108, 37 and 32 pixel font heights.
numFontSize = 0.100           # Number and fixation font height
textFontSize = 0.034          # Instructions, breaks and feedback font height
probeFontSize = 0.030         # Thought-probe font height
textFont = "Courier New" if platform.system() == "Windows" else "Monaco"
# Preserve the chosen monospaced style with a Windows-compatible font.
textWidthFraction = 0.82      # Use at most 82% of the window width
textMaxWidth = 1.45           # Reading-width cap, in window-height units
goStimDuration = 0.700        # Stim display duration, in seconds
maskDuration = 3.000          # Fixation-mask duration, in seconds
breakDuration = 30.0          # Break between experimental blocks, in seconds
restingStateDuration = 180.0  # Three minutes for EACH pre/post resting section
restingDotRadius = 0.005      # Radius in window-height units (~5.4 px at 1080p)
probeKeys = ["1", "2", "3", "4", "5"]
probeBlocks = [1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20]  # Which experimental blocks are followed by a probe

# Name of CSV and whereit is, By default it will be in a folder called CSV, and called "SART_Stimuli(Stimuli).csv"
DEFAULT_STIMULI_FILE = "CSV/SART_Stimuli(Stimuli).csv"

# ----------------------------
# Eye Link Setup
# ----------------------------
dummy_mode = dumb               # Make sure this is False to use EyeLink
use_retina = False              # Mostly to avoid issues with Colin's Laptop
sampling_rate_hz = 1000         # Requested EyeLink sampling rate

# Assigned only when a session is launched, never when this module is imported.
edf_file = None
session_identifier = None
session_folder = None


def initialize_session(output_root=""):
    """Create a unique session beside the script (or under the supplied root)."""
    global edf_file, session_identifier, session_folder
    allowed = set(ascii_letters + digits + "_")
    while True:
        values = {"EDF filename (1-8 letters, digits or underscore)": "Test"}
        dlg = gui.DlgFromDict(values, title="EyeLink EDF filename", sortKeys=False)
        if not dlg.OK:
            raise ExperimentAbort("EDF filename dialog cancelled")
        name = str(next(iter(values.values()))).strip()
        if name.lower().endswith(".edf"):
            name = name[:-4]
        if 1 <= len(name) <= 8 and set(name) <= allowed:
            break
        error = {"Message": "Use 1-8 letters, digits or underscores."}
        gui.DlgFromDict(error, title="Invalid EDF filename", fixed=["Message"])
    edf_file = name + ".EDF"
    root = Path(output_root).expanduser() if output_root else Path(__file__).resolve().parent / "results"
    root.mkdir(parents=True, exist_ok=True)
    session_identifier = name + datetime.now().strftime("_%Y_%m_%d_%H_%M_%S_%f")
    folder = root / session_identifier
    folder.mkdir(exist_ok=False)
    session_folder = str(folder.resolve())
    print(f"Session output: {session_folder}")
    print("DUMMY MODE: no real eye data." if dummy_mode else "HARDWARE MODE: EyeLink at 100.1.1.1")


class ExperimentAbort(Exception):
    """Leave the task through its finally blocks, including EDF recovery."""


class EyeLinkSession:
    def __init__(self):
        self.tracker = None
        self.edf_open = False
        self.recording_attempted = False
        self.recording = False
        self.graphics_open = False
        self.active_trial = None
        self.closed = False
        self.last_check = 0.0
        self.outcome = "SART_ERROR"

    def connect(self):
        self.tracker = pylink.EyeLink(None if dummy_mode else "100.1.1.1")
        if not dummy_mode:
            result = self.tracker.openDataFile(edf_file)
            if result not in (None, 0):
                raise RuntimeError(f"openDataFile failed: {result}")
            self.edf_open = True
        # Configure the tracker
        self.tracker.setOfflineMode() # Put in offline mode before we change tracking 
        eyelink_ver = 0  # Dummy mode; query Host software version on hardware

        if not dummy_mode:
            vstr = self.tracker.getTrackerVersionString()
            eyelink_ver = int(vstr.split()[-1].split('.')[0])

            # print out some debug info 
            print('Running experiment on %s, version %d' % (vstr, eyelink_ver))

        # File and Link data control
        # what eye events to save in the EDF file, include everything by default
        file_event_flags = 'LEFT,RIGHT,FIXATION,SACCADE,BLINK,MESSAGE,BUTTON,INPUT'

        # what eye events to make available over the link, include everything by default
        link_event_flags = 'LEFT,RIGHT,FIXATION,SACCADE,BLINK,BUTTON,FIXUPDATE,INPUT'

        if eyelink_ver > 3:
            file_sample_flags = 'LEFT,RIGHT,GAZE,HREF,RAW,AREA,HTARGET,GAZERES,BUTTON,STATUS,INPUT'
            link_sample_flags = 'LEFT,RIGHT,GAZE,GAZERES,AREA,HTARGET,STATUS,INPUT'

        else:
            file_sample_flags = 'LEFT,RIGHT,GAZE,HREF,RAW,AREA,GAZERES,BUTTON,STATUS,INPUT'
            link_sample_flags = 'LEFT,RIGHT,GAZE,GAZERES,AREA,STATUS,INPUT'

        self.tracker.sendCommand("file_event_filter = %s" % file_event_flags)
        self.tracker.sendCommand("file_sample_data = %s" % file_sample_flags)
        self.tracker.sendCommand("link_event_filter = %s" % link_event_flags)
        self.tracker.sendCommand("link_sample_data = %s" % link_sample_flags)

        # Set the requested rate while offline, before calibration.
        self.set_sampling_rate()
        # HV9 is nine calibration locations; eye selection remains on the Host.
        self.tracker.sendCommand("calibration_type = HV9")


    def set_sampling_rate(self):
        if dummy_mode:
            return
        result = self.tracker.sendCommand(f"sample_rate = {sampling_rate_hz}")
        if result not in (None, 0):
            raise RuntimeError(f"EyeLink rejected {sampling_rate_hz} Hz: {result}")
        pylink.pumpDelay(100)
        print(f"EyeLink sampling rate requested: {sampling_rate_hz} Hz. "
              "Verify the actual rate in the Host/EDF metadata.")

    def start(self, win):
        self.connect()
        width, height = (int(value) for value in win.size)
        coords = f"0 0 {width - 1} {height - 1}"
        self.tracker.sendCommand(f"screen_pixel_coords = {coords}")
        self.message(f"DISPLAY_COORDS {coords}")
        if not dummy_mode:
            self.graphics = EyeLinkCoreGraphicsPsychoPy(self.tracker, win)
            self.graphics.setCalibrationColors(sartLight, sartDark)
            if use_retina:
                self.graphics.fixMacRetinaDisplay()
            pylink.openGraphicsEx(self.graphics)
            self.graphics_open = True
            calibration_instructions = make_task_text(
                win, height=textFontSize, color=sartLight, alignText="left",
                text=("EyeLink calibration and validation\n\n"
                      "Operator: position the participant and check the camera image.\n\n"
                      "Press C to open EyeLink setup. Calibrate, then validate, "
                      "using the Host controls.\n\n"
                      "Review the validation results before leaving setup.\n\n"
                      "Escape cancels this session."))
            wait_for_key(win, calibration_instructions, key="c")
            while True:
                self.tracker.setOfflineMode()
                pylink.pumpDelay(100)
                self.message("CALIBRATION_SETUP_START")
                result = self.tracker.doTrackerSetup()
                if result not in (None, 0):
                    raise ExperimentAbort(f"Tracker setup returned {result}")
                if not self.tracker.isConnected() or self.tracker.breakPressed():
                    raise ExperimentAbort("Tracker setup aborted/disconnected")
                self.message("CALIBRATION_SETUP_EXIT")
                confirmation = make_task_text(
                    win, height=textFontSize, color=sartLight, alignText="left",
                    text=("Operator: check EyeLink validation results\n\n"
                          "Press V only if calibration AND validation were completed "
                          "and the results meet your lab's criteria.\n\n"
                          "Press C to return to EyeLink setup.\n\n"
                          "Escape cancels this session.\n\n"
                          "This is a manual confirmation; the program does not "
                          "automatically assess validation accuracy."))
                event.clearEvents()
                while True:
                    confirmation.draw()
                    win.flip()
                    if not self.tracker.isConnected() or self.tracker.breakPressed():
                        raise ExperimentAbort("Tracker disconnected/Host aborted")
                    keys = event.getKeys(keyList=["v", "c", "escape"])
                    if "escape" in keys:
                        abort_task()
                    if "c" in keys or "v" in keys:
                        break
                if "c" in keys:
                    continue
                self.message("VALIDATION_ACCEPTED_BY_OPERATOR")
                break
        else:
            print("DUMMY MODE: calibration/validation skipped; no real eye data.")
        event.clearEvents()
        self.tracker.setOfflineMode()
        pylink.pumpDelay(100)
        # Reapply after setup in case the Host settings were changed there.
        self.set_sampling_rate()
        # Attempt flag also covers exceptions after the Host starts recording.
        self.recording_attempted = True
        result = self.tracker.startRecording(1, 1, 1, 1)
        if result != 0:
            raise RuntimeError(f"EyeLink startRecording failed: {result}")
        self.recording = True
        pylink.pumpDelay(100)
        self.check(force=True)
        self.message("SART_START")
        if not dummy_mode:
            self.message(f"REQUESTED_SAMPLE_RATE_HZ {sampling_rate_hz}")
        self.message(f"SESSION {session_identifier}")

    def message(self, text):
        if self.tracker is not None:
            self.tracker.sendMessage(str(text).replace("\n", " ").replace("\r", " "))

    def variable(self, name, value):
        self.message(f"!V TRIAL_VAR {name} {value}")

    def begin_trial(self, identifier, variables):
        self.check(force=True)
        self.active_trial = identifier
        self.message(f"TRIALID {identifier}")
        for name, value in variables.items():
            self.variable(name, value)

    def end_trial(self):
        self.message("TRIAL_RESULT 0")
        self.active_trial = None

    def check(self, force=False):
        if self.tracker is None:
            return
        now = time.monotonic()
        if not force and now - self.last_check < 0.05:
            return
        self.last_check = now
        if not self.tracker.isConnected() or self.tracker.breakPressed():
            raise ExperimentAbort("EyeLink disconnected or Host aborted")
        if not self.recording:
            return
        # isRecording is a return code, NOT a boolean: TRIAL_OK == 0.
        try:
            status = self.tracker.isRecording()
        except RuntimeError as error:
            raise ExperimentAbort(f"EyeLink recording failed: {error}") from error
        if status != pylink.TRIAL_OK:
            raise ExperimentAbort(f"EyeLink recording return code: {status}")

    def cleanup(self):
        if self.closed:
            return
        self.closed = True
        errors = []

        def attempt(label, action):
            try:
                action()
                return True
            except (Exception, KeyboardInterrupt) as error:
                errors.append(f"{label}: {error}")
                return False

        if self.tracker is not None:
            if self.active_trial is not None:
                attempt("aborted trial", lambda: self.variable("aborted", 1))
                attempt("trial result", lambda: self.message(
                    f"TRIAL_RESULT {pylink.ABORT_EXPT}"))
            attempt("session outcome", lambda: self.message(self.outcome))
            # Kolin: do not use isRecording() as a boolean or as a cleanup gate.
            if self.recording_attempted:
                attempt("recording tail", lambda: pylink.pumpDelay(100))
                attempt("stop recording", self.tracker.stopRecording)
            self.recording = False
            attempt("offline mode", self.tracker.setOfflineMode)
            attempt("offline settling", lambda: pylink.pumpDelay(500))
            if self.edf_open:
                closed = attempt("close EDF", self.tracker.closeDataFile)
                if closed:
                    self.edf_open = False
                    destination = str(Path(session_folder).resolve() / edf_file)

                    def transfer():
                        received = self.tracker.receiveDataFile(edf_file, destination)
                        if received is not None and received < 0:
                            raise RuntimeError(f"transfer returned {received}")
                        if not Path(destination).is_file() or Path(destination).stat().st_size == 0:
                            raise RuntimeError("No nonempty local EDF was received")
                        print(f"EDF saved to: {destination}")

                    attempt("transfer EDF (recover from Host if unsuccessful)", transfer)
            if self.graphics_open:
                attempt("close calibration graphics", pylink.closeGraphics)
            attempt("close tracker connection", self.tracker.close)
        if dummy_mode:
            print("Dummy mode: no real EDF is recorded or transferred.")
        if errors:
            report = (f"Host EDF: {edf_file}\nSession: {session_folder}\n"
                      + "\n".join(errors))
            print("EyeLink cleanup/recovery information:\n" + report)
            attempt("write recovery note", lambda: (Path(session_folder) /
                    "EDF_recovery.txt").write_text(report, encoding="utf-8"))


eye_session = EyeLinkSession()


def abort_task():
    raise ExperimentAbort("Participant pressed Escape")


def checked_wait(duration):
    """Keep the original feedback duration while allowing Escape/Host abort."""
    clock = core.Clock()
    while clock.getTime() < duration:
        eye_session.check()
        if "escape" in event.getKeys(keyList=["escape"]):
            abort_task()
        core.wait(min(0.005, max(0, duration - clock.getTime())))


# ------------------------------------------------------------------
# START SART
# ------------------------------------------------------------------
def sart(
    monitor="testMonitor",
    practice=True,
    path="",
    stimuli_file=DEFAULT_STIMULI_FILE,
):
    """
    Run the SART using a CSV-defined trial sequence.

    The CSV determines:
      - the number of practice and experimental blocks,
      - the number of trials in each block,
      - the stimulus shown on every trial,
      - whether each trial is Go or No-Go,
      - the order of all blocks and trials.

    Experimental thought probes occur only after block numbers listed
    in the global probeBlocks variable.

    Pre/post resting sections are scheduled in code, independent of CSV rows.
    Legacy CSV rows whose Type is "RestingState" are ignored to avoid duplicates.

    Required CSV columns:
      Order, Type, Block, Trial, Stimuli, Go/No-Go
    """
    global eye_session
    eye_session = EyeLinkSession()
    participant_number = part_info_gui()

    stimuli_path = resolve_stimuli_path(stimuli_file)
    task_rows = load_stimuli_csv(stimuli_path)

    practice_blocks = group_blocks(task_rows, "Practice")
    experiment_blocks = group_blocks(task_rows, "Experiment")
    omit_num = determine_omit_number(task_rows)

    if not experiment_blocks:
        raise ValueError("The CSV does not contain any Experiment trials.")
    initialize_session(path)
    output_directory = Path(session_folder)
    metadata = {
        "participant_number": participant_number,
        "session_identifier": session_identifier,
        "dummy_mode": dummy_mode,
        "requested_sampling_rate_hz": sampling_rate_hz,
        "calibration_type": "HV9",
        "eye_selection": "Configured on Host",
        "stimuli_file": str(stimuli_path.resolve()),
        "font": textFont,
        "number_height": numFontSize,
        "instruction_height": textFontSize,
        "probe_height": probeFontSize,
        "resting_duration_s": restingStateDuration,
        "go_stimulus_max_duration_s": goStimDuration,
        "response_ends_stimulus": True,
        "mask_duration_s": maskDuration,
    }
    (output_directory / "session_info.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8")

    results_path = output_directory / f"SART_{participant_number}.txt"
    probes_path = output_directory / f"SART_{participant_number}_probes.txt"

    trial_results = []
    probe_results = []

    win = visual.Window(
        fullscr=full_screen,
        color=sartDark,
        units="height",
        monitor=monitor,
    )

    try:
        win.mouseVisible = False
        metadata["display_pixels"] = [int(value) for value in win.size]
        eye_session.start(win)
        eye_session.message(f"PARTICIPANT {participant_number}")
        pupillometry_resting_state(win, "Pre")
        sart_init_inst(win, omit_num, practice and bool(practice_blocks))

        if practice and practice_blocks:
            sart_prac_inst(win, omit_num)

            for probe_number, block in enumerate(practice_blocks, start=1):
                sart_block(
                    win=win, block=block, feedback=True,
                    font_size=numFontSize, results_sink=trial_results,
                )

                probe_results.append(
                    thought_probe(
                        win=win,
                        phase="Practice",
                        block_name=block["name"],
                        probe_num=probe_number,
                    )
                )
                probe_continue_inst(win)

        sart_act_task_inst(win)

        for probe_number, block in enumerate(experiment_blocks, start=1):
            sart_block(
                win=win, block=block, feedback=False,
                font_size=numFontSize, results_sink=trial_results,
            )

            if probe_number in probeBlocks:
                probe_results.append(
                    thought_probe(
                        win=win,
                        phase="Experiment",
                        block_name=block["name"],
                        probe_num=probe_number,
                    )
                )
                probe_continue_inst(win)

            if probe_number < len(experiment_blocks):
                sart_break_inst(win, breakDuration)

        write_trial_results(
            results_path,
            participant_number,
            trial_results,
        )
        write_probe_results(
            probes_path,
            participant_number,
            probe_results,
        )

        # Save behavioral results before the final rest, including if it is aborted.
        pupillometry_resting_state(win, "Post")
        eye_session.outcome = "SART_END"

    except (ExperimentAbort, KeyboardInterrupt):
        eye_session.outcome = "SART_ABORT"
        raise
    finally:
        # Stop/recover the EDF even if saving one behavioral file fails.
        try:
            eye_session.cleanup()
        finally:
            try:
                metadata["outcome"] = eye_session.outcome
                save_actions = [
                    ("trial results", lambda: write_trial_results(
                        results_path, participant_number, trial_results)),
                    ("probe results", lambda: write_probe_results(
                        probes_path, participant_number, probe_results)),
                    ("session metadata", lambda: (output_directory / "session_info.json").write_text(
                        json.dumps(metadata, indent=2), encoding="utf-8")),
                ]
                for label, action in save_actions:
                    try:
                        action()
                    except Exception as error:
                        print(f"ERROR saving {label}: {error}")
            finally:
                win.close()



def resolve_stimuli_path(stimuli_file):
    """
    Resolve a relative CSV path.

    First checks beside this Python file, then checks the current
    working directory.
    """
    supplied_path = Path(stimuli_file)

    if supplied_path.is_absolute() and supplied_path.exists():
        return supplied_path

    script_directory = Path(__file__).resolve().parent
    beside_script = script_directory / supplied_path

    if beside_script.exists():
        return beside_script

    working_directory = Path.cwd() / supplied_path

    if working_directory.exists():
        return working_directory

    raise FileNotFoundError(
        f"Could not find the stimuli CSV: {stimuli_file}\n"
        f"Checked:\n"
        f"  {beside_script}\n"
        f"  {working_directory}"
    )


def load_stimuli_csv(csv_path):
    """
    Load and validate the SART trial CSV.

    RestingState rows are deliberately ignored.
    """
    required_columns = {
        "Order",
        "Type",
        "Block",
        "Trial",
        "Stimuli",
        "Go/No-Go",
    }

    rows = []

    with csv_path.open("r", newline="", encoding="utf-8-sig") as csv_file:
        reader = csv.DictReader(csv_file)

        if reader.fieldnames is None:
            raise ValueError("The stimuli CSV has no header row.")

        missing_columns = required_columns - set(reader.fieldnames)
        if missing_columns:
            raise ValueError(
                "The stimuli CSV is missing required columns: "
                + ", ".join(sorted(missing_columns))
            )

        for source_row_number, row in enumerate(reader, start=2):
            trial_type = (row.get("Type") or "").strip()

            # Resting sections are scheduled in code before/after the SART.
            if trial_type.casefold() == "restingstate":
                continue

            if trial_type not in {"Practice", "Experiment"}:
                raise ValueError(
                    f"Unexpected Type '{trial_type}' on CSV row "
                    f"{source_row_number}."
                )

            missing_values = [name for name in required_columns if row.get(name) is None]
            if missing_values:
                raise ValueError(f"Missing cells on CSV row {source_row_number}: "
                                 + ", ".join(sorted(missing_values)))
            response_type = normalise_response_type(row["Go/No-Go"])

            try:
                order = int(row["Order"])
            except ValueError as error:
                raise ValueError(
                    f"Order must be an integer on CSV row "
                    f"{source_row_number}."
                ) from error

            stimulus = row["Stimuli"].strip()
            block_name = row["Block"].strip()
            trial_label = row["Trial"].strip()

            if not stimulus:
                raise ValueError(
                    f"Stimuli is blank on CSV row {source_row_number}."
                )

            if not block_name:
                raise ValueError(
                    f"Block is blank on CSV row {source_row_number}."
                )

            rows.append(
                {
                    "order": order,
                    "type": trial_type,
                    "block": block_name,
                    "trial": trial_label,
                    "stimulus": stimulus,
                    "response_type": response_type,
                    "source_row": source_row_number,
                }
            )

    if not rows:
        raise ValueError(
            "No Practice or Experiment trials were found in the CSV."
        )

    rows.sort(key=lambda row: row["order"])

    orders = [row["order"] for row in rows]
    if len(orders) != len(set(orders)):
        raise ValueError(
            "The Order column contains duplicate values among the "
            "Practice and Experiment trials."
        )

    seen_blocks = set()
    last_block = None
    experiment_seen = False
    for row in rows:
        block_key = (row["type"], row["block"])
        if row["type"] == "Experiment":
            experiment_seen = True
        elif experiment_seen:
            raise ValueError("Practice rows must precede Experiment rows in CSV Order.")
        if block_key != last_block:
            if block_key in seen_blocks:
                raise ValueError(f"Block {block_key} is split across CSV Order. "
                                 "Keep each block's trials together.")
            seen_blocks.add(block_key)
            last_block = block_key
    return rows


def normalise_response_type(value):
    cleaned = value.strip().casefold().replace("_", "-").replace(" ", "")

    if cleaned == "go":
        return "Go"

    if cleaned in {"no-go", "nogo"}:
        return "No-Go"

    raise ValueError(
        f"Go/No-Go must contain 'Go' or 'No-Go'; found '{value}'."
    )


def group_blocks(rows, phase):
    """
    Group ordered CSV rows into blocks while preserving their first
    appearance in the CSV.
    """
    blocks_by_name = {}
    ordered_blocks = []

    for row in rows:
        if row["type"] != phase:
            continue

        block_name = row["block"]

        if block_name not in blocks_by_name:
            block = {
                "name": block_name,
                "phase": phase,
                "trials": [],
            }
            blocks_by_name[block_name] = block
            ordered_blocks.append(block)

        blocks_by_name[block_name]["trials"].append(row)

    return ordered_blocks


def determine_omit_number(rows):
    """
    Determine the No-Go number for the instruction screens.
    Scoring uses the CSV's Go/No-Go column on every trial.
    """
    no_go_stimuli = {
        row["stimulus"]
        for row in rows
        if row["response_type"] == "No-Go"
    }

    if len(no_go_stimuli) != 1:
        raise ValueError(
            "The instruction screen expects one consistent No-Go "
            "stimulus, but the CSV contains: "
            + ", ".join(sorted(no_go_stimuli))
        )

    return next(iter(no_go_stimuli))


def part_info_gui():
    while True:
        values = {"Participant Number": ""}
        dlg = gui.DlgFromDict(values, title="SART", sortKeys=False)
        if not dlg.OK:
            raise ExperimentAbort("Participant dialog cancelled")
        participant = str(values["Participant Number"]).strip()
        if participant and all(c in ascii_letters + digits + "_-" for c in participant):
            return participant
        error = {"Message": "Enter a participant ID using letters, digits, - or _."}
        gui.DlgFromDict(error, title="Invalid participant ID", fixed=["Message"])


def make_task_text(win, **kwargs):
    """Screen-relative type and wrapping for task text (not calibration UI).

    Height units use the same scale on both axes, keeping letters proportional.
    The reading area follows the actual window aspect ratio, with side margins.
    """
    aspect_ratio = float(win.size[0]) / float(win.size[1])
    kwargs.setdefault("units", "height")
    kwargs.setdefault("font", textFont)
    kwargs.setdefault("wrapWidth", min(textMaxWidth,
                                      textWidthFraction * aspect_ratio))
    kwargs.setdefault("anchorHoriz", "center")
    kwargs.setdefault("anchorVert", "center")
    return visual.TextStim(win, **kwargs)


def pupillometry_resting_state(win, phase):
    """Record a resting baseline

    No countdown or other stimulus is shown during fixation.
    A separate summary is appended after each section, including on abort.
    """
    prompt = (
        "In the following task, you will see a fixation point in the center "
        "of the screen. We will ask you to sit in a relaxed position and "
        "fixate on this point for 3 minutes while keeping your mind free "
        "from thoughts. You are welcome to blink as you normally would."
        "\n\n\n\nIf you ever need to stop, please feel free to ask."
        "\n\nPress b when you are ready to begin."
    )
    instructions = make_task_text(
        win, text=prompt, height=textFontSize, color=sartLight,
        pos=(0, 0), alignText="left",
    )
    dot = visual.Circle(
        win, units="height", radius=restingDotRadius, pos=(0, 0),
        fillColor=sartLight, lineColor=sartLight, edges=64,
    )
    clock = core.Clock()
    state = {"started": False, "duration": "NA", "status": "aborted"}

    def onset():
        clock.reset()
        state["started"] = True
        eye_session.message(f"RESTING_STATE_START {phase}")

    def offset():
        state["duration"] = clock.getTime()
        eye_session.message(f"RESTING_STATE_END {phase}")

    try:
        wait_for_key(win, instructions)
        eye_session.begin_trial(
            f"REST_{phase}",
            {"trial_kind": "pupillometry_resting_state", "phase": phase,
             "requested_duration_s": restingStateDuration},
        )
        event.clearEvents()
        dot.draw()
        win.callOnFlip(onset)
        win.flip()
        while clock.getTime() < restingStateDuration:
            eye_session.check()
            if "escape" in event.getKeys(keyList=["escape"]):
                abort_task()
            dot.draw()
            win.flip()
        # First background-only frame ends fixation; mark that same flip.
        eye_session.check(force=True)
        if "escape" in event.getKeys(keyList=["escape"]):
            abort_task()
        win.callOnFlip(offset)
        win.flip()
        eye_session.variable("actual_duration_s", f"{state['duration']:.6f}")
        eye_session.end_trial()
        state["status"] = "completed"
    finally:
        if state["started"] and state["status"] != "completed":
            state["duration"] = clock.getTime()
            try:
                eye_session.message(f"RESTING_STATE_ABORT {phase}")
            except Exception:
                pass  # Main cleanup still attempts EDF close/transfer.
        # This summary is separate from gaze samples, which remain in the EDF.
        summary_path = Path(session_folder) / "resting_state_summary.tsv"
        try:
            needs_header = not summary_path.exists() or summary_path.stat().st_size == 0
            with summary_path.open("a", newline="", encoding="utf-8") as output:
                writer = csv.DictWriter(output, delimiter="\t", fieldnames=[
                    "phase", "requested_duration_s", "actual_duration_s", "status",
                ])
                if needs_header:
                    writer.writeheader()
                writer.writerow({
                    "phase": phase,
                    "requested_duration_s": restingStateDuration,
                    "actual_duration_s": (f"{state['duration']:.6f}"
                                          if state["started"] else "NA"),
                    "status": state["status"],
                })
        except OSError as error:
            print(f"Could not save resting-state summary: {error}")


def wait_for_key(win, stimulus, key="b"):
    event.clearEvents()

    while True:
        eye_session.check()
        stimulus.draw()
        win.flip()

        keys = event.getKeys(keyList=[key, "escape"])

        if "escape" in keys:
            abort_task()

        if key in keys:
            return


def sart_init_inst(win, omit_num, has_practice):
    ending = (
        "\n\nWe will begin with some practice trials."
        if has_practice
        else ""
    )

    inst = make_task_text(
        win,
        text=(
            "For the following task, you will see a series of numbers "
            "from 1 to 9.\n"
            "When you see a number appear on the screen, press the "
            "spacebar.\n\n"
            f"However, when you see the number {omit_num}, do not "
            "respond.\n"
            "Try to respond as quickly and accurately as possible,\n"
            "but it is more important to be correct than fast."
            f"{ending}\n\n"
            "Press b to begin."
        ),
        color=sartLight,
        height=textFontSize,
        pos=(0, 0),
        alignText="left",
    )

    wait_for_key(win, inst)


def sart_prac_inst(win, omit_num):
    inst = make_task_text(
        win,
        text=(
            "Remember: press the spacebar when you see any number "
            f"except {omit_num}.\n\n"
            "Press b to start the practice."
        ),
        color=sartLight,
        height=textFontSize,
        pos=(0, 0),
        alignText="left",
    )

    wait_for_key(win, inst)


def sart_act_task_inst(win):
    inst = make_task_text(
        win,
        text=(
            "We will now start the actual task.\n\n"
            "Give equal importance to accuracy and speed.\n\n"
            "Press b to start the actual task."
        ),
        color=sartLight,
        height=textFontSize,
        pos=(0, 0),
        alignText="left",
    )

    wait_for_key(win, inst)



def probe_continue_inst(win):
    """Pause after a thought probe before the next trial or break."""
    inst = make_task_text(
        win,
        text="Press b to continue task.",
        color=sartLight,
        height=textFontSize,
        pos=(0, 0),
    )

    wait_for_key(win, inst)


def sart_break_inst(win, duration):
    break_message = make_task_text(
        win,
        text=f"You will now have a {int(duration)} second break.",
        color=sartLight,
        height=textFontSize,
        pos=(0, 0),
    )

    continue_message = make_task_text(
        win,
        text="Press b to continue.",
        color=sartLight,
        height=textFontSize,
        pos=(0, 0),
    )

    break_clock = core.Clock()

    while break_clock.getTime() < duration:
        eye_session.check()
        break_message.draw()
        win.flip()

        if "escape" in event.getKeys(keyList=["escape"]):
            abort_task()

    wait_for_key(win, continue_message)


def sart_block(win, block, feedback, font_size, results_sink=None):
    """
    Present one CSV-defined block in its exact CSV order.
    """
    mouse = event.Mouse(visible=False, win=win)

    fixation_stim = make_task_text(
        win,
        text="+",
        height=font_size,
        color=sartLight,
        pos=(0, 0),
    )

    number_stim = make_task_text(
        win,
        color=sartLight,
        pos=(0, 0),
        height=font_size,
    )

    correct_stim = make_task_text(
        win,
        text="CORRECT",
        color="lightgreen",
        height=textFontSize,
        pos=(0, 0),
    )

    incorrect_stim = make_task_text(
        win,
        text="INCORRECT",
        color="#cc7777",
        height=textFontSize,
        pos=(0, 0),
    )

    result_list = []
    block_clock = core.Clock()

    for trial_in_block, trial in enumerate(block["trials"], start=1):
        result_list.append(
            sart_trial(
                win=win,
                feedback=feedback,
                fixation_stim=fixation_stim,
                number_stim=number_stim,
                correct_stim=correct_stim,
                incorrect_stim=incorrect_stim,
                font_size=font_size,
                trial=trial,
                trial_in_block=trial_in_block,
                block_name=block["name"],
                phase=block["phase"],
                mouse=mouse,
            )
        )

        if results_sink is not None:
            results_sink.append(result_list[-1])

    total_block_time = block_clock.getTime()
    mean_trial_time = total_block_time / len(block["trials"])

    for result in result_list:
        result["mean_trial_time_s"] = mean_trial_time
        result["block_duration_s"] = total_block_time

    print(
        f"\n#### {block['phase']} — {block['name']} ####\n"
        f"Trials: {len(block['trials'])}\n"
        f"Mean time per trial: {mean_trial_time * 1000:.3f} ms\n"
    )

    return result_list


def thought_probe(win, phase, block_name, probe_num):
    probe_text = (
        "Please characterize your current conscious experience using "
        "the number keys on the keyboard.\n\n"
        "1. I am totally focused on the current task.\n\n"
        "2. I am thinking about my performance on the task or how "
        "long it is taking.\n\n"
        "3. I am distracted by sights, sounds, temperature, or "
        "physical sensations.\n\n"
        "4. I am daydreaming or my mind is wandering about things "
        "unrelated to the task.\n\n"
        "5. I am not very alert, my mind is blank, or I am drowsy."
    )

    probe_stim = make_task_text(
        win,
        text=probe_text,
        color=sartLight,
        height=probeFontSize,
        pos=(0, 0),
        alignText="left",
    )

    event.clearEvents()
    probe_clock = core.Clock()
    eye_session.begin_trial(
        f"PROBE_{phase}_{probe_num}",
        {"trial_kind": "thought_probe", "phase": phase,
         "block": block_name, "probe_number": probe_num},
    )
    first_frame = True

    while True:
        eye_session.check()
        if first_frame:
            win.callOnFlip(event.clearEvents, eventType="keyboard")
            win.callOnFlip(probe_clock.reset)
            win.callOnFlip(eye_session.message,
                           f"PROBE_ONSET {phase} {block_name} {probe_num}")
            first_frame = False
        probe_stim.draw()
        win.flip()

        keys = event.getKeys(
            keyList=probeKeys + ["escape"],
            timeStamped=probe_clock,
        )

        if not keys:
            continue

        if any(key == "escape" for key, _ in keys):
            abort_task()
        key, response_time = keys[0]

        eye_session.message(f"PROBE_RESPONSE {key} RT {response_time:.6f}")
        eye_session.variable("probe_response", key)
        eye_session.variable("probe_RT", f"{response_time:.6f}")
        eye_session.end_trial()
        return {
            "phase": phase,
            "block": block_name,
            "probe_number": probe_num,
            "response": key,
            "response_time_s": response_time,
        }


def sart_trial(
    win,
    feedback,
    fixation_stim,
    number_stim,
    correct_stim,
    incorrect_stim,
    font_size,
    trial,
    trial_in_block,
    block_name,
    phase,
    mouse,
):
    """
    Run one SART trial and score it using the CSV Go/No-Go value.
    """
    mouse.setVisible(False)
    eye_session.begin_trial(
        f"SART_{trial['order']}",
        {"phase": phase, "block": block_name,
         "trial_in_block": trial_in_block, "csv_order": trial["order"],
         "csv_trial": trial["trial"], "stimulus": trial["stimulus"],
         "go_no_go": trial["response_type"]},
    )

    number_stim.setHeight(font_size)
    number_stim.setText(trial["stimulus"])

    trial_clock = core.Clock()
    response_clock = core.Clock()

    number_stim.draw()
    event.clearEvents()

    # Clear pre-onset keys and reset on the flip that makes the number visible.
    win.callOnFlip(event.clearEvents, eventType="keyboard")
    win.callOnFlip(response_clock.reset)
    win.callOnFlip(trial_clock.reset)
    win.callOnFlip(eye_session.message, "STIM_ONSET")
    win.flip()

    response_rt = None

    while trial_clock.getTime() < goStimDuration:
        eye_session.check()
        keys = event.getKeys(
            keyList=["space", "escape"],
            timeStamped=response_clock,
        )

        if keys:
            if any(key == "escape" for key, _ in keys):
                abort_task()
            key, key_time = keys[0]

            response_rt = key_time
            eye_session.message(f"RESPONSE space RT {response_rt:.6f}")
            break

    fixation_stim.draw()
    win.callOnFlip(eye_session.message, "MASK_ONSET")
    win.flip()

    mask_clock = core.Clock()

    while mask_clock.getTime() < maskDuration:
        eye_session.check()
        if "escape" in event.getKeys(keyList=["escape"]):
            abort_task()

        # Redraw so the fixation remains on screen
        fixation_stim.draw()
        win.flip()

    responded = response_rt is not None
    expected_response = trial["response_type"] == "Go"
    response_accuracy = int(responded == expected_response)

    if feedback:
        if response_accuracy:
            correct_stim.draw()
        else:
            incorrect_stim.draw()

        win.flip()
        checked_wait(0.700)
        win.flip()

    trial_duration = trial_clock.getTime()
    eye_session.variable("responded", int(responded))
    eye_session.variable("accuracy", response_accuracy)
    eye_session.variable("RT", f"{response_rt:.6f}" if responded else "NA")
    if not responded:
        eye_session.message("NO_RESPONSE")
    eye_session.end_trial()

    return {
        "phase": phase,
        "block": block_name,
        "trial_in_block": trial_in_block,
        "csv_order": trial["order"],
        "csv_trial": trial["trial"],
        "stimulus": trial["stimulus"],
        "go_no_go": trial["response_type"],
        "responded": int(responded),
        "response_accuracy": response_accuracy,
        "response_rt_s": (
            f"{response_rt:.6f}" if response_rt is not None else "NA"
        ),
        "trial_duration_s": trial_duration,
    }


def write_trial_results(output_path, participant_number, results):
    fieldnames = [
        "participant_number",
        "phase",
        "block",
        "trial_in_block",
        "csv_order",
        "csv_trial",
        "stimulus",
        "go_no_go",
        "responded",
        "response_accuracy",
        "response_rt_s",
        "trial_duration_s",
        "mean_trial_time_s",
        "block_duration_s",
    ]

    temporary_path = output_path.with_suffix(output_path.suffix + ".tmp")
    with temporary_path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(
            output_file,
            fieldnames=fieldnames,
            delimiter="\t",
        )
        writer.writeheader()

        for result in results:
            writer.writerow(
                {
                    "participant_number": participant_number,
                    **result,
                }
            )

    os.replace(temporary_path, output_path)


def write_probe_results(output_path, participant_number, results):
    fieldnames = [
        "participant_number",
        "phase",
        "block",
        "probe_number",
        "response",
        "response_time_s",
    ]

    temporary_path = output_path.with_suffix(output_path.suffix + ".tmp")
    with temporary_path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(
            output_file,
            fieldnames=fieldnames,
            delimiter="\t",
        )
        writer.writeheader()

        for result in results:
            writer.writerow(
                {
                    "participant_number": participant_number,
                    **result,
                }
            )

    os.replace(temporary_path, output_path)


def main():
    try:
        sart()
    except (ExperimentAbort, KeyboardInterrupt) as error:
        eye_session.outcome = "SART_ABORT"
        print(f"Task aborted: {error}")
    finally:
        # Covers CSV/dialog/window failures before sart's window finally exists.
        eye_session.cleanup()


if __name__ == "__main__":
    main()
