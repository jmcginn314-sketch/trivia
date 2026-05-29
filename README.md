# Trivia Streamlit App

This is a simple Streamlit trivia game with a 1,000-question reserve bank.

## Add Questions

The included `questions.csv` was built from `1000_moderately_hard_trivia_questions.xlsx`.

If you replace it later, keep these columns:

```csv
question,option_a,option_b,option_c,option_d,answer,category,difficulty
What planet is known as the Red Planet?,Venus,Mars,Jupiter,Saturn,B,Science,Easy
```

The `answer` column can be `A`, `B`, `C`, `D`, or the exact answer text. For typed-answer questions, alternate accepted answers can be separated with `|` or `;`.

You can also upload a CSV or JSON file from inside the app. JSON should be a list like this:

```json
[
  {
    "question": "What planet is known as the Red Planet?",
    "choices": ["Venus", "Mars", "Jupiter", "Saturn"],
    "answer": "Mars",
    "category": "Science",
    "difficulty": "Easy"
  }
]
```

## Run

For Streamlit Cloud, upload this folder and use `app.py` as the main file.

To run locally, install Streamlit, then run:

```powershell
streamlit run app.py
```

Or:

```powershell
python -m streamlit run app.py
```
