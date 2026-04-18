import streamlit as st
import os
import json
import time
import random
from google import genai
from google.genai import types
from dotenv import load_dotenv

# --- CONFIGURATION & SECURITY ---
st.set_page_config(page_title="LBE UTBK 2026 Quiz", page_icon="🎓", layout="wide")
load_dotenv()

# --- MOBILE UI PATCH ---
st.markdown("""
<style>
    .stMarkdown p { line-height: 1.7 !important; margin-bottom: 15px !important; font-size: 16px !important; }
    div[role="radiogroup"] > label { margin-bottom: 14px !important; padding: 4px 0px; }
    .element-container:has(table) { overflow-x: auto; }
    @media (max-width: 768px) {
        .block-container { padding-top: 2rem !important; padding-left: 1.2rem !important; padding-right: 1.2rem !important; }
        h1 { font-size: 26px !important; }
        h3 { font-size: 20px !important; }
    }
</style>
""", unsafe_allow_html=True)

# --- SESSION STATE INITIALIZATION ---
if "quiz_data" not in st.session_state:
    st.session_state.quiz_data = None
if "submitted" not in st.session_state:
    st.session_state.submitted = False
if "last_request_time" not in st.session_state:
    st.session_state.last_request_time = 0
if "quiz_vault" not in st.session_state:         
    st.session_state.quiz_vault = []             

# --- THE ENGINE ROOM (Prompt Splitter) ---
LITE_CONSTRAINTS = """
CRITICAL DISTRACTOR CALIBRATION (LITE-MODEL OVERRIDE):
You must strictly engineer the options using this exact blueprint:
- 1 Option is the CORRECT ANSWER. It must be concise and NEVER the longest option.
- 1 Option is the EXACT MATCH TRAP. Copy a phrase exactly from the text, but twist the context so it is factually wrong for the question.
- 1 Option is the HALF-RIGHT TRAP. Make the first half of the sentence perfectly accurate, but make the conclusion completely false.
- 2 Options are PLAUSIBLE but ultimately incorrect logical leaps.
- OPTION SYMMETRY: All 5 options MUST be visually similar in length. 
***FORMAT 7 EXCEPTION: If the user selects Format 7 (True/False), completely ignore the 5-option rule. Your options array MUST contain exactly two strings: ["Benar", "Salah"].***
"""

FLASH_CONSTRAINTS = """
ADVANCED HOTS CALIBRATION (FLASH MODEL):
You must strictly engineer the options to mimic real UTBK SNBT HOTS standards:
- 1 Option is the CORRECT ANSWER. Ensure it requires deep synthesis of the text.
- 1 Option is the EXACT MATCH TRAP. Use verbatim text from the passage but apply it to the wrong context.
- 1 Option is the HALF-RIGHT TRAP. Plausible premise, but a factually incorrect conclusion.
- 2 Options are highly plausible distractors based on common logical fallacies.
- OPTION SYMMETRY: Keep all 5 options relatively symmetrical in length.
***FORMAT 7 EXCEPTION: If the user selects Format 7 (True/False), completely ignore the 5-option rule. Your options array MUST contain exactly two strings: ["Benar", "Salah"].***
"""

JSON_SCHEMA = """
{
  "text": "String (The reading passage formatted with markdown. Use a markdown table if Format 3).",
  "questions": [
    {
      "question_stem": "String (The question, OR the declarative statement to be evaluated if Format 7)",
      "trap_planning": "String (CRITICAL: Before writing the options, briefly state your plan for the distractors)",
      "options": ["String (5 options for MCQs, OR just 'Benar' and 'Salah' for Format 7)"],
      "correct_answer_index": Integer (0-based index for the correct option),
      "explanation": "String (Explain the correct answer. CRITICAL: THIS EXPLANATION MUST BE WRITTEN ENTIRELY IN BAHASA INDONESIA, explaining the logic clearly to an Indonesian student.)"
    }
  ]
}
"""

def get_prompt_template(format_choice, topic, model_choice):
    base_intro = f"You are an expert UTBK SNBT item creator for Literasi Bahasa Inggris (LBE) 2026. Create a reading module about: {topic}.\n"
    
    if format_choice == "1":
        specifics = "1. TEXT: Write a semi-academic text of 300-400 words.\n2. QUESTIONS: 4 questions (Main Idea, Inference, Relationship, Vocabulary). Randomize the question stems."
    elif format_choice == "2":
        specifics = "1. TEXT: Write TWO separate passages (A and B), 200 words each.\n2. QUESTIONS: 4 questions (Synthesis, Cross-Text Agreement, Authorial Response, Differential Inference)."
    elif format_choice == "3":
        specifics = "1. TEXT: Format as a digital forum thread. YOU MUST FORMAT THE THREAD AS A STRICT MARKDOWN TABLE with two columns: 'User' and 'Post Content'. Include User1 and 5 distinct replies.\n2. QUESTIONS: 4 questions (Debate Trajectory, User Alignment, Logical Evaluation, Intent/Tone)."
    elif format_choice == "4":
        specifics = "1. TEXT: Write a scientific text (300 words) with specific data/percentages.\n2. QUESTIONS: 4 questions (Quantitative Inference, Data Interpretation, Main Idea, Flaw)."
    elif format_choice == "5":
        specifics = "1. TEXT: Write a scientific text (300 words) that explicitly includes a mathematical or physics formula. YOU MUST format the formula using LaTeX syntax (e.g., $$ E = mc^2 $$). Explain the variables in English.\n2. QUESTIONS: 4 questions. DO NOT ask the student to calculate numbers. Ask them to infer the inverse/direct relationships of the variables based on the text reading."
    elif format_choice == "6": 
        specifics = "1. TEXT: Write an analytical Soshum text (300-400 words) focusing on sociology or history.\n2. QUESTIONS: 4 questions (Author's Tone, Societal Inference, Argumentative Structure, Social Causality)."
    else:
        specifics = "1. TEXT: Write an analytical text of 300-400 words.\n2. QUESTIONS: Provide 4 declarative statements based on the text. The student must evaluate if the statement is True or False. Use the Format 7 Exception."
        
    constraints = LITE_CONSTRAINTS if model_choice == "gemini-2.5-flash-lite" else FLASH_CONSTRAINTS
    json_rules = f"\nCRITICAL OUTPUT FORMAT: Output strictly in JSON format matching this schema:\n{JSON_SCHEMA}" 
    
    return base_intro + specifics + constraints + json_rules

# --- VISUAL FRONTEND ---
st.title("🎓 Interactive UTBK LBE 2026")

with st.sidebar:
    st.header("🔑 Authentication")
    user_api_key = st.text_input("Enter your Gemini API Key:", type="password", placeholder="Paste your key here...")
    
    with st.expander("❓ How to get a FREE API key"):
        st.markdown("**It takes 30 seconds and is completely free:**\n1. Go to [Google AI Studio](https://aistudio.google.com/app/apikey).\n2. Sign in with your Google Account.\n3. Click **Create API key**.\n4. Copy and paste it above.")
        
    st.divider()
    
    st.header("⚙️ Generator Settings")
    
    model_display = st.selectbox(
        "Select AI Model:",
        ["Gemini 2.5 Flash Lite (Faster)", "Gemini 2.5 Flash (Smarter)"]
    )
    selected_model_id = "gemini-2.5-flash-lite" if "Lite" in model_display else "gemini-2.5-flash"
    
    # NEW: Expanded Dropdown Menu!
    format_choice = st.selectbox(
        "Select Format:", 
        [
            "1. Standard Text", 
            "2. Dual Passages", 
            "3. Digital Thread (Table)", 
            "4. Quantitative/Saintek (Standard Science)", 
            "5. Quantitative/Saintek (Math Formula Integration)", 
            "6. Soshum", 
            "7. True/False Statements"
        ]
    )
    user_topic = st.text_input("Topic:", placeholder="Leave blank for random...")
    
    if st.button("🚀 Generate Quiz", type="primary", use_container_width=True):
        if not user_api_key:
            st.error("⚠️ Please enter your Gemini API Key first!")
        elif len(user_api_key) < 35:
            st.warning("⚠️ That doesn't look like a valid Google API key. It should be longer.")
        else:
            current_time = time.time()
            time_since_last = current_time - st.session_state.last_request_time
            
            if time_since_last < 60:
                st.warning(f"⏳ API Cooldown Active. Please wait {int(60 - time_since_last)} seconds.")
            else:
                st.session_state.last_request_time = current_time
                
                with st.spinner(f"Generating interactive quiz using {selected_model_id}..."):
                    client = genai.Client(api_key=user_api_key) 
                    format_num = format_choice.split(".")[0]
                    
                    if user_topic.strip():
                        final_topic = user_topic.strip()
                    else:
                        diverse_topics = ["modern pop culture and social media", "economics and bizarre business trends", "sports history or e-sports", "arts and music history", "a weird historical event", "urban legends or human behavior", "global food trends", "modern moral dilemmas"]
                        final_topic = random.choice(diverse_topics)
                    
                    prompt = get_prompt_template(format_num, final_topic, selected_model_id)
                    
                    try:
                        response = client.models.generate_content(
                            model=selected_model_id, 
                            contents=prompt,
                            config=types.GenerateContentConfig(
                                response_mime_type="application/json"
                            )
                        )
                        
                        raw_text = response.text.replace("```json", "").replace("```", "").strip()
                        
                        st.session_state.quiz_data = json.loads(raw_text)
                        st.session_state.submitted = False
                        
                    except json.JSONDecodeError as e:
                        st.error("The AI made a syntax error while formatting the JSON. Click generate again.")
                        print(f"JSON ERROR: {e}\nRAW TEXT:\n{raw_text}")
                    except Exception as e:
                        error_msg = str(e)
                        if "429" in error_msg:
                            st.warning("🚦 The server is busy! Hit speed limit. Try again in 15 seconds.")
                        else:
                            st.error(f"Generation Error: {e}")

    # --- THE OFFLINE VAULT ---
    st.divider()
    st.header("🗄️ Offline Quiz Vault")
    
    if st.session_state.quiz_data:
        if st.button("💾 Save Current Quiz to Vault", use_container_width=True):
            quiz_copy = st.session_state.quiz_data.copy()
            quiz_copy["source_model"] = selected_model_id 
            st.session_state.quiz_vault.append(quiz_copy)
            st.success(f"Added! Vault now holds {len(st.session_state.quiz_vault)} quizzes.")
            
    if len(st.session_state.quiz_vault) > 0:
        st.info(f"📦 Quizzes ready for download: {len(st.session_state.quiz_vault)}")
        vault_json = json.dumps(st.session_state.quiz_vault, indent=2)
        st.download_button(
            label="📥 Download Vault (JSON)",
            data=vault_json,
            file_name="utbk_lbe_offline_bank.json",
            mime="application/json",
            type="primary",
            use_container_width=True
        )
        if st.button("🗑️ Clear Vault", use_container_width=True):
            st.session_state.quiz_vault = []
            st.rerun()

# --- INTERACTIVE QUIZ UI ---
if st.session_state.quiz_data:
    quiz = st.session_state.quiz_data
    
    st.markdown("### Reading Passage")
    st.markdown(quiz.get("text", "Text missing."), unsafe_allow_html=True)
    st.divider()
    
    st.markdown("### Questions")
    user_answers = {}
    
    # DETECT IF IT IS A TRUE/FALSE TABLE
    is_true_false_format = False
    if quiz.get("questions") and len(quiz["questions"]) > 0:
        first_options = quiz["questions"][0].get("options", [])
        if len(first_options) == 2 and ("Benar" in first_options or "True" in first_options):
            is_true_false_format = True

    if is_true_false_format:
        # RENDER AS UTBK TABLE
        st.markdown("**(Evaluasi Pernyataan: Pilih Benar atau Salah untuk setiap pernyataan di bawah ini)**")
        st.write("")
        
        # Table Headers
        header1, header2 = st.columns([3, 1])
        header1.markdown("**Pernyataan**")
        header2.markdown("**Pilihan**")
        st.markdown("---")
        
        for i, q in enumerate(quiz.get("questions", [])):
            col1, col2 = st.columns([3, 1])
            col1.write(q.get('question_stem', 'Question missing'))
            
            user_answers[i] = col2.radio(
                f"Select answer for {i+1}", 
                options=q.get("options", ["Benar", "Salah"]), 
                key=f"q_{i}", 
                horizontal=True,
                label_visibility="collapsed"
            )
            st.markdown("<hr style='margin: 10px 0px; opacity: 0.2;'>", unsafe_allow_html=True)
            
    else:
        # RENDER AS STANDARD MULTIPLE CHOICE
        for i, q in enumerate(quiz.get("questions", [])):
            st.markdown(f"**{i+1}. {q.get('question_stem', 'Question missing')}**")
            user_answers[i] = st.radio(f"Select answer for {i+1}", options=q.get("options", []), key=f"q_{i}", label_visibility="collapsed")
            st.write("") 
    
    if not st.session_state.submitted:
        if st.button("Submit Answers", type="primary"):
            st.session_state.submitted = True
            st.rerun()

    if st.session_state.submitted:
        st.divider()
        st.markdown("### 📊 Results & Explanations")
        
        score = 0
        for i, q in enumerate(quiz.get("questions", [])):
            correct_index = q.get("correct_answer_index", q.get("correct_answer", q.get("answer", 0)))
            
            # GRADER FIX: Safely catch "Benar" / "Salah" strings if the AI hallucinated the index
            if isinstance(correct_index, str):
                clean_char = correct_index.strip().upper().replace('"', '')
                if clean_char in ["BENAR", "TRUE"]: 
                    correct_index = 0
                elif clean_char in ["SALAH", "FALSE"]: 
                    correct_index = 1
                else:
                    correct_index = {"A": 0, "B": 1, "C": 2, "D": 3, "E": 4}.get(clean_char, 0) 
            
            try:
                correct_index = int(correct_index)
                if correct_index < 0 or correct_index > 4: correct_index = 0
            except ValueError:
                correct_index = 0

            options = q.get("options", [])
            if options and len(options) > correct_index:
                correct_text = options[correct_index]
                user_text = user_answers[i]
                
                if user_text == correct_text:
                    score += 1
                    st.success(f"**Question {i+1}: Correct!**")
                else:
                    st.error(f"**Question {i+1}: Incorrect.** \n\nYou chose: {user_text} \n\nCorrect answer: {correct_text}")
                
                explanation_text = q.get("explanation", q.get("trap_planning", "No explanation provided."))
                st.info(f"**Penjelasan:** {explanation_text}")
                st.write("---")
            
        st.subheader(f"Final Score: {score} / 4")
        if st.button("Reset Quiz"):
            st.session_state.submitted = False
            st.rerun()
