from __future__ import annotations

import csv
import io
import json
import random
import re
import time
from pathlib import Path
from typing import Any

import streamlit as st
import streamlit.components.v1 as components


APP_DIR = Path(__file__).parent
DEFAULT_QUESTION_FILE = APP_DIR / "questions.csv"


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


def answer_matches(selected_answer: str, correct_answer: str) -> bool:
    accepted_answers = re.split(r"\s*[|;]\s*", correct_answer)
    selected = normalize_answer(selected_answer)
    return any(selected == normalize_answer(answer) for answer in accepted_answers if answer)


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


def load_uploaded_questions(uploaded_file: Any) -> list[dict[str, Any]]:
    if not uploaded_file:
        return []
    contents = uploaded_file.getvalue().decode("utf-8-sig")
    if uploaded_file.name.lower().endswith(".json"):
        return parse_json_questions(contents)
    return parse_csv_questions(contents)


def reset_game() -> None:
    for key in [
        "player_name",
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


def start_game(player_name: str, questions: list[dict[str, Any]], count: int, shuffle: bool) -> None:
    question_order = list(questions)
    if shuffle:
        random.shuffle(question_order)
    st.session_state.player_name = player_name.strip()
    st.session_state.game_questions = question_order[:count]
    st.session_state.current_index = 0
    st.session_state.score = 0
    st.session_state.answers = []
    st.session_state.started_at = time.time()
    st.session_state.stopped_at = None
    st.session_state.submitted_answer = None
    st.session_state.is_answer_submitted = False


def submit_answer(question: dict[str, Any], selected_answer: str) -> None:
    correct = answer_matches(selected_answer, question["answer"])
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


def mark_last_answer_correct() -> None:
    if st.session_state.answers and not st.session_state.answers[-1]["is_correct"]:
        st.session_state.answers[-1]["is_correct"] = True
        st.session_state.score += 1


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
    default_questions = load_default_questions(str(DEFAULT_QUESTION_FILE), default_modified_at)

    with st.sidebar:
        st.header("Questions")
        uploaded_file = st.file_uploader("Use a CSV or JSON question bank", type=["csv", "json"])
        uploaded_questions = load_uploaded_questions(uploaded_file)
        active_questions = uploaded_questions or default_questions
        source_name = uploaded_file.name if uploaded_file else DEFAULT_QUESTION_FILE.name
        st.caption(f"Loaded {len(active_questions)} questions from {source_name}.")

    if not active_questions:
        st.warning("Add questions to questions.csv or upload a CSV/JSON question bank to start.")
        return

    if "game_questions" not in st.session_state:
        with st.form("start_form"):
            player_name = st.text_input("Name", placeholder="Put your name in")
            question_count = st.number_input(
                "Questions this round",
                min_value=1,
                max_value=len(active_questions),
                value=len(active_questions),
                step=1,
            )
            shuffle_questions = st.checkbox("Shuffle questions", value=True)
            start = st.form_submit_button("Start game", use_container_width=True)
            if start:
                if not player_name.strip():
                    st.error("Enter a name to start.")
                else:
                    start_game(player_name, active_questions, int(question_count), shuffle_questions)
                    st.rerun()
        st.info("Replace questions.csv with your full reserve bank whenever you are ready.")
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
        )
    else:
        selected_answer = st.text_input("Your answer", disabled=st.session_state.is_answer_submitted)

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
            if not question["choices"] and st.button("Count my answer as correct", use_container_width=True):
                mark_last_answer_correct()
                st.rerun()

        label = "Finish" if st.session_state.current_index == total_questions - 1 else "Next question"
        if st.button(label, use_container_width=True):
            move_next()
            st.rerun()


if __name__ == "__main__":
    main()
