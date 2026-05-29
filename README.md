[README.md](https://github.com/user-attachments/files/28408760/README.md)
# Trivia Streamlit App

This is a simple Streamlit trivia game with a 100-question Jeopardy-style multiple-choice reserve bank.

Players choose a category, then a round code. Full rounds have 20 questions; smaller categories use one shorter category round.

Choose `All categories` to use the full 100-question bank. With the included file, that creates `round1` through `round5`.

Answer choices come from the source workbook. For future typed-answer imports, the app can still generate choices from the question bank.

## Add Questions

The included `questions.csv` was built from `100_original_jeopardy_style_multiple_choice (1).xlsx`.

If you replace it later, keep these columns:

```csv
question,option_a,option_b,option_c,option_d,answer,category,difficulty
What planet is known as the Red Planet?,Venus,Mars,Jupiter,Saturn,B,Science,Easy
```

The `answer` column can be `A`, `B`, `C`, `D`, or the exact answer text. For typed-answer questions, alternate accepted answers can be separated with `|` or `;`.

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
