from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import random
import re
import time
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import streamlit as st
import streamlit.components.v1 as components


APP_DIR = Path(__file__).parent
DEFAULT_QUESTION_FILE = APP_DIR / "questions.csv"
ROUND_SIZE = 20
ROUND_SEED = "fixed-trivia-rounds-v3-jeopardy"
ALL_CATEGORIES = "All categories"
CHOICE_COUNT = 4


def format_elapsed(seconds: float) -> str:
    total_seconds = max(0, int(seconds))
    minutes, secs = divmod(total_seconds, 60)
    hours, mins = divmod(minutes, 60)
    if hours:
        return f"{hours}:{mins:02d}:{secs:02d}"
    return f"{mins}:{secs:02d}"


def clean(value: Any) -> str:
    return str(value or "").strip()


def normalize_answer(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", clean(value).casefold()).strip()


def remove_leading_article(value: str) -> str:
    return re.sub(r"^(a|an|the)\s+", "", value).strip()


def text_similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, left, right).ratio()


def asks_for_person(question_text: str) -> bool:
    question = normalize_answer(question_text)
    person_cues = {
        "artist",
        "author",
        "composer",
        "director",
        "emperor",
        "explorer",
        "founder",
        "inventor",
        "king",
        "leader",
        "novelist",
        "painter",
        "philosopher",
        "playwright",
        "poet",
        "president",
        "queen",
        "scientist",
        "singer",
        "writer",
    }
    return question.startswith("who") or any(cue in question.split() for cue in person_cues)


def fuzzy_answer_matches(selected_answer: str, correct_answer: str) -> bool:
    selected = remove_leading_article(normalize_answer(selected_answer))
    correct = remove_leading_article(normalize_answer(correct_answer))
    if not selected or not correct:
        return False
    if selected == correct:
        return True
    if min(len(selected), len(correct)) < 5:
        return False

    length_gap = abs(len(selected) - len(correct)) / max(len(selected), len(correct))
    if length_gap > 0.35:
        return False

    sorted_selected = " ".join(sorted(selected.split()))
    sorted_correct = " ".join(sorted(correct.split()))
    threshold = 0.86 if max(len(selected), len(correct)) >= 8 else 0.92
    return max(text_similarity(selected, correct), text_similarity(sorted_selected, sorted_correct)) >= threshold


def last_name_matches(selected_answer: str, correct_answer: str, question_text: str) -> bool:
    selected = remove_leading_article(normalize_answer(selected_answer))
    correct = remove_leading_article(normalize_answer(correct_answer))
    correct_parts = correct.split()
    if len(correct_parts) < 2 or len(correct_parts) > 4:
        return False
    if not asks_for_person(question_text):
        return False

    suffixes = {"jr", "sr", "ii", "iii", "iv", "v"}
    if correct_parts[-1] in suffixes and len(correct_parts) > 2:
        correct_parts = correct_parts[:-1]

    last_name = correct_parts[-1]
    if len(last_name) < 4:
        return False

    place_prefixes = {
        "new",
        "north",
        "south",
        "east",
        "west",
        "united",
        "great",
        "mount",
        "lake",
        "saint",
        "st",
    }
    if correct_parts[0] in place_prefixes:
        return False

    surname_particles = {"da", "de", "del", "di", "du", "la", "le", "van", "von"}
    surname_forms = {last_name}
    if len(correct_parts) >= 2 and correct_parts[-2] in surname_particles:
        surname_forms.add(" ".join(correct_parts[-2:]))

    return selected in surname_forms


def answer_matches(selected_answer: str, correct_answer: str, question_text: str = "") -> bool:
    accepted_answers = re.split(r"\s*[|;]\s*", correct_answer)
    return any(
        fuzzy_answer_matches(selected_answer, answer)
        or last_name_matches(selected_answer, answer, question_text)
        for answer in accepted_answers
        if answer
    )


def game_code_seed(game_code: str) -> int:
    normalized = clean(game_code).casefold()
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def round_count_for(questions: list[dict[str, Any]]) -> int:
    if not questions:
        return 0
    return math.ceil(len(questions) / ROUND_SIZE)


def round_codes_for(questions: list[dict[str, Any]]) -> list[str]:
    return [f"round{index}" for index in range(1, round_count_for(questions) + 1)]


def category_options_for(questions: list[dict[str, Any]]) -> list[str]:
    categories = sorted({question["category"] for question in questions if question["category"]})
    return [ALL_CATEGORIES, *categories]


def questions_for_category(questions: list[dict[str, Any]], category: str) -> list[dict[str, Any]]:
    if category == ALL_CATEGORIES:
        return questions
    return [question for question in questions if question["category"] == category]


def answer_marker(answer: str) -> str:
    return normalize_answer(answer)


def unique_wrong_answers(questions: list[dict[str, Any]], correct_answer: str) -> list[str]:
    correct_marker = answer_marker(correct_answer)
    answers = []
    seen = {correct_marker}
    for question in questions:
        answer = clean(question["answer"])
        marker = answer_marker(answer)
        if not answer or not marker or marker in seen:
            continue
        seen.add(marker)
        answers.append(answer)
    return answers


def add_multiple_choice_options(
    round_questions: list[dict[str, Any]],
    category_questions: list[dict[str, Any]],
    all_questions: list[dict[str, Any]],
    category: str,
    game_code: str,
) -> list[dict[str, Any]]:
    questions_with_choices = []
    for index, question in enumerate(round_questions):
        correct_answer = clean(question["answer"])
        if question["choices"]:
            updated_question = dict(question)
            updated_question["round_position"] = index + 1
            questions_with_choices.append(updated_question)
            continue

        wrong_answers = unique_wrong_answers(category_questions, correct_answer)
        if len(wrong_answers) < CHOICE_COUNT - 1:
            wrong_answers = unique_wrong_answers(all_questions, correct_answer)

        seed_parts = [
            ROUND_SEED,
            category,
            game_code,
            str(question["id"]),
            question["question"],
            "choices",
        ]
        rng = random.Random(game_code_seed("|".join(seed_parts)))
        distractors = rng.sample(wrong_answers, min(CHOICE_COUNT - 1, len(wrong_answers)))
        choices = unique_choices([correct_answer, *distractors])
        rng.shuffle(choices)

        updated_question = dict(question)
        updated_question["choices"] = choices
        updated_question["round_position"] = index + 1
        questions_with_choices.append(updated_question)
    return questions_with_choices


def build_round_questions(questions: list[dict[str, Any]], category: str, game_code: str) -> list[dict[str, Any]]:
    normalized = clean(game_code).casefold()
    round_number = int(normalized.removeprefix("round")) - 1
    category_questions = questions_for_category(questions, category)
    question_order = list(category_questions)
    random.Random(game_code_seed(f"{ROUND_SEED}|{category}")).shuffle(question_order)
    start = round_number * ROUND_SIZE
    round_questions = question_order[start : start + ROUND_SIZE]
    return add_multiple_choice_options(round_questions, category_questions, questions, category, game_code)


def first_value(row: dict[str, Any], *names: str) -> str:
    lowered = {key.lower().strip(): value for key, value in row.items()}
    for name in names:
        value = lowered.get(name.lower())
        if clean(value):
            return clean(value)
    return ""


def unique_choices(choices: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for choice in choices:
        normalized = choice.strip()
        if not normalized:
            continue
        marker = normalized.casefold()
        if marker in seen:
            continue
        seen.add(marker)
        result.append(normalized)
    return result


def normalize_question(row: dict[str, Any], index: int) -> dict[str, Any] | None:
    question = first_value(row, "question", "prompt", "clue", "text")
    answer = first_value(row, "answer", "correct_answer", "correct", "solution")
    category = first_value(row, "category", "topic")
    difficulty = first_value(row, "difficulty", "level")

    choices = unique_choices(
        [
            first_value(row, "option_a", "a", "choice_a", "choice1", "wrong_answer_1"),
            first_value(row, "option_b", "b", "choice_b", "choice2", "wrong_answer_2"),
            first_value(row, "option_c", "c", "choice_c", "choice3", "wrong_answer_3"),
            first_value(row, "option_d", "d", "choice_d", "choice4", "wrong_answer_4"),
        ]
    )

    if isinstance(row.get("choices"), list):
        choices = unique_choices([clean(choice) for choice in row["choices"]])
    elif first_value(row, "choices", "options"):
        raw_choices = first_value(row, "choices", "options")
        separator = "|" if "|" in raw_choices else ";"
        choices = unique_choices(raw_choices.split(separator))

    if answer.casefold() in {"a", "b", "c", "d"} and choices:
        selected_index = ord(answer.casefold()) - ord("a")
        if 0 <= selected_index < len(choices):
            answer = choices[selected_index]

    if answer and answer not in choices and choices:
        choices.append(answer)

    if not question or not answer:
        return None

    return {
        "id": index,
        "question": question,
        "answer": answer,
        "choices": choices,
        "category": category,
        "difficulty": difficulty,
    }


def parse_csv_questions(contents: str) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(contents))
    questions = []
    for index, row in enumerate(reader, start=1):
        normalized = normalize_question(row, index)
        if normalized:
            questions.append(normalized)
    return questions


def parse_json_questions(contents: str) -> list[dict[str, Any]]:
    data = json.loads(contents)
    if isinstance(data, dict):
        data = data.get("questions", [])
    questions = []
    for index, item in enumerate(data, start=1):
        if isinstance(item, dict):
            normalized = normalize_question(item, index)
            if normalized:
                questions.append(normalized)
    return questions


@st.cache_data(show_spinner=False)
def load_default_questions(path: str, modified_at: float) -> list[dict[str, Any]]:
    question_path = Path(path)
    if not question_path.exists():
        return []
    contents = question_path.read_text(encoding="utf-8-sig")
    if question_path.suffix.lower() == ".json":
        return parse_json_questions(contents)
    return parse_csv_questions(contents)


def reset_game() -> None:
    for key in [
        "player_name",
        "category",
        "game_code",
        "game_questions",
        "current_index",
        "score",
        "answers",
        "started_at",
        "stopped_at",
        "submitted_answer",
        "is_answer_submitted",
    ]:
        st.session_state.pop(key, None)
    for key in list(st.session_state.keys()):
        if str(key).startswith("answer_"):
            st.session_state.pop(key, None)


def start_game(player_name: str, category: str, game_code: str, questions: list[dict[str, Any]]) -> None:
    st.session_state.player_name = player_name.strip()
    st.session_state.category = category
    st.session_state.game_code = game_code.strip()
    st.session_state.game_questions = build_round_questions(questions, category, game_code)
    st.session_state.current_index = 0
    st.session_state.score = 0
    st.session_state.answers = []
    st.session_state.started_at = time.time()
    st.session_state.stopped_at = None
    st.session_state.submitted_answer = None
    st.session_state.is_answer_submitted = False


def submit_answer(question: dict[str, Any], selected_answer: str) -> None:
    correct = answer_matches(selected_answer, question["answer"], question["question"])
    if correct:
        st.session_state.score += 1
    st.session_state.answers.append(
        {
            "question": question["question"],
            "selected": selected_answer,
            "correct_answer": question["answer"],
            "is_correct": correct,
            "category": question["category"],
        }
    )
    st.session_state.submitted_answer = selected_answer
    st.session_state.is_answer_submitted = True


def move_next() -> None:
    st.session_state.current_index += 1
    st.session_state.submitted_answer = None
    st.session_state.is_answer_submitted = False
    if st.session_state.current_index >= len(st.session_state.game_questions):
        st.session_state.stopped_at = time.time()


def render_live_timer(started_at: float) -> None:
    start_ms = int(started_at * 1000)
    components.html(
        f"""
        <div style="font-family: system-ui, -apple-system, Segoe UI, sans-serif;">
          <div style="font-size: 0.78rem; color: #64748b; margin-bottom: 0.2rem;">Time</div>
          <div id="live-timer" style="font-size: 1.7rem; font-weight: 700; color: #111827;">0:00</div>
        </div>
        <script>
          const start = {start_ms};
          const target = document.getElementById("live-timer");
          function formatElapsed(totalSeconds) {{
            totalSeconds = Math.max(0, Math.floor(totalSeconds));
            const hours = Math.floor(totalSeconds / 3600);
            const minutes = Math.floor((totalSeconds % 3600) / 60);
            const seconds = totalSeconds % 60;
            if (hours > 0) {{
              return `${{hours}}:${{String(minutes).padStart(2, "0")}}:${{String(seconds).padStart(2, "0")}}`;
            }}
            return `${{minutes}}:${{String(seconds).padStart(2, "0")}}`;
          }}
          function tick() {{
            target.textContent = formatElapsed((Date.now() - start) / 1000);
          }}
          tick();
          setInterval(tick, 1000);
        </script>
        """,
        height=72,
    )


def render_scoreboard(total_questions: int) -> None:
    elapsed_until = st.session_state.stopped_at or time.time()
    elapsed = elapsed_until - st.session_state.started_at

    with st.sidebar:
        st.subheader("Game")
        st.write(f"Player: **{st.session_state.player_name}**")
        category = st.session_state.get("category", "")
        if category:
            st.write(f"Category: **{category}**")
        game_code = st.session_state.get("game_code", "")
        if game_code:
            st.write(f"Code: **{game_code}**")
        col_a, col_b = st.columns(2)
        col_a.metric("Score", f"{st.session_state.score}/{total_questions}")
        col_b.metric("Question", f"{min(st.session_state.current_index + 1, total_questions)}/{total_questions}")
        if st.session_state.stopped_at:
            st.metric("Final Time", format_elapsed(elapsed))
        else:
            render_live_timer(st.session_state.started_at)
        if st.button("End game", use_container_width=True):
            st.session_state.stopped_at = time.time()
            st.rerun()


def render_review() -> None:
    with st.expander("Review answers", expanded=False):
        for number, answer in enumerate(st.session_state.answers, start=1):
            status = "Correct" if answer["is_correct"] else "Incorrect"
            st.markdown(f"**{number}. {status}**")
            st.write(answer["question"])
            st.write(f"Your answer: {answer['selected']}")
            if not answer["is_correct"]:
                st.write(f"Correct answer: {answer['correct_answer']}")


def main() -> None:
    st.set_page_config(page_title="Trivia Game", layout="centered")
    st.title("Trivia Game")

    default_modified_at = DEFAULT_QUESTION_FILE.stat().st_mtime if DEFAULT_QUESTION_FILE.exists() else 0
    active_questions = load_default_questions(str(DEFAULT_QUESTION_FILE), default_modified_at)

    if not active_questions:
        st.warning("Add questions to questions.csv to start.")
        return
    if "game_questions" not in st.session_state:
        player_name = st.text_input("Name", placeholder="Put your name in")
        category = st.selectbox("Category", category_options_for(active_questions))
        category_questions = questions_for_category(active_questions, category)
        round_codes = round_codes_for(category_questions)
        if not round_codes:
            st.warning(f"{category} needs at least {ROUND_SIZE} questions to start.")
            return
        game_code = st.selectbox("Round code", round_codes)
        st.caption(
            f"{len(round_codes)} rounds available in {category}. "
            f"Each round gives everyone the same multiple-choice questions."
        )
        start = st.button("Start game", use_container_width=True)
        if start:
            if not player_name.strip():
                st.error("Enter a name to start.")
            else:
                start_game(player_name, category, game_code, active_questions)
                st.rerun()
        return

    total_questions = len(st.session_state.game_questions)
    render_scoreboard(total_questions)

    if st.session_state.stopped_at:
        elapsed = st.session_state.stopped_at - st.session_state.started_at
        percent = round((st.session_state.score / total_questions) * 100)
        st.success(
            f"{st.session_state.player_name} finished with {st.session_state.score}/{total_questions} "
            f"({percent}%) in {format_elapsed(elapsed)}."
        )
        render_review()
        if st.button("Start over", use_container_width=True):
            reset_game()
            st.rerun()
        return

    question = st.session_state.game_questions[st.session_state.current_index]

    details = " | ".join(item for item in [question["category"], question["difficulty"]] if item)
    if details:
        st.caption(details)
    st.subheader(question["question"])

    selected_answer = ""
    if question["choices"]:
        selected_answer = st.radio(
            "Choose an answer",
            question["choices"],
            index=None,
            disabled=st.session_state.is_answer_submitted,
            key=f"answer_{st.session_state.current_index}",
        )
    else:
        selected_answer = st.text_input(
            "Your answer",
            disabled=st.session_state.is_answer_submitted,
            key=f"answer_{st.session_state.current_index}",
        )

    if not st.session_state.is_answer_submitted:
        can_submit = bool(selected_answer and selected_answer.strip())
        if st.button("Submit answer", disabled=not can_submit, use_container_width=True):
            submit_answer(question, selected_answer)
            st.rerun()
    else:
        last_answer = st.session_state.answers[-1]
        if last_answer["is_correct"]:
            st.success("Correct.")
        else:
            st.error(f"Incorrect. Correct answer: {question['answer']}")

        label = "Finish" if st.session_state.current_index == total_questions - 1 else "Next question"
        if st.button(label, use_container_width=True):
            move_next()
            st.rerun()


if __name__ == "__main__":
    main()
