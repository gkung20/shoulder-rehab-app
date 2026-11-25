"""The app follows only the patient when someone else is in view."""
import random
from dataclasses import replace

from src.config import ExerciseConfig
from src.person_lock import PersonLock
from src.session_processor import SessionProcessor
from src.synthetic_pose import body, rep_angles


def farther(person, factor=.7):
    """The same person seen farther away (smaller, around their chest)."""
    landmarks, world = person
    cx = (landmarks[11].x + landmarks[12].x) / 2
    return [type(p)(cx + (p.x - cx) * factor, .25 + (p.y - .25) * factor, p.visibility) for p in landmarks], world


def test_the_lock_keeps_the_patient_when_someone_crosses_behind():
    lock = PersonLock()
    assert lock.choose([body(40., center=.55)]) == 0  # the session starts with the patient
    rng = random.Random(3)
    for step in range(60):
        stranger = farther(body(0., center=.95 - step * .015))  # walks behind, right to left
        people = [body(40., center=.55), stranger]
        rng.shuffle(people)                     # the model gives people in any order
        index = lock.choose(people)
        assert people[index][0][11].x == body(40., center=.55)[0][11].x


def test_the_closest_person_is_locked_first_and_strangers_alone_are_refused():
    lock = PersonLock()
    near = body(0, center=.55)
    far = [type(p)(p.x * .6 + .3, p.y * .6 + .1, p.visibility) for p in body(0, center=.7)[0]]  # smaller: farther
    assert lock.choose([(far, None), near]) == 1
    assert lock.choose([body(0, center=1.05)]) is None  # alone, elsewhere: not the patient
    assert lock.choose([body(0, center=.6)]) == 0       # the patient back in place
    lock.reset()
    assert lock.choose([body(0, center=1.05)]) == 0     # a new session locks again


def test_a_stranger_alone_never_counts_movements():
    config = ExerciseConfig.from_yaml()
    config = replace(config, calibration=replace(config.calibration, duration_sec=.6), filtering=replace(config.filtering, ema_alpha=1))
    processor = SessionProcessor(config)
    lock = PersonLock()
    reps, t = 0, 0.
    for _ in range(30):  # the patient calibrates
        chosen = lock.choose([body(0, center=.5)])
        pts, world = body(0, center=.5)
        processor.process(pts if chosen is not None else None, world, 640, 480, t)
        t += 1 / 30
    for angle in rep_angles() * 2:  # the patient has gone; a stranger exercises elsewhere
        frame = [body(angle, center=1.1)]
        chosen = lock.choose(frame)
        landmarks, world = frame[chosen] if chosen is not None else (None, None)
        reps += processor.process(landmarks, world, 640, 480, t).new_evaluation is not None
        t += 1 / 30
    assert reps == 0
