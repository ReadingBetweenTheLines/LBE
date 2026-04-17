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

# --- THE ENGINE ROOM ---
UNIVERSAL_CONSTRAINTS = """
CRITICAL DISTRACTOR CALIBRATION (LITE-MODEL OVERRIDE):
You must strictly engineer the 5 options (A, B, C, D, E) using this exact blueprint:
- 1 Option is the CORRECT ANSWER. It must be concise and NEVER the longest option.
- 1 Option is the EXACT MATCH TRAP. Copy a phrase exactly from the text, but twist the context so it is factually wrong for the question.
- 1 Option is the HALF-RIGHT TRAP. Make the first half of the sentence perfectly accurate, but make the conclusion completely false.
- 2 Options are PLAUSIBLE but ultimately incorrect logical leaps.
- OPTION SYMMETRY: All 5 options MUST be visually similar in length. 
"""

JSON_SCHEMA = """
{
  "text": "String (The reading passage formatted with markdown. Use a markdown table if Format 3).",
  "questions": [
    {
      "question_stem": "String",
      "trap_planning": "String (CRITICAL: Before writing the options, briefly state your plan for the Exact Match and Half-Right traps)",
      "options": ["String", "String", "String", "String", "String"],
      "correct_answer_index": Integer (0 for A, 1 for B, 2 for C, 3 for D, 4 for E),
      "explanation": "String (Explain the correct answer and explicitly point out the Exact Match and Half-Right traps)"
    }
  ]
}
"""

def get_prompt_template(format_choice, topic):
    base_intro = f"You are an expert UTBK SNBT item creator for Literasi Bahasa Inggris (LBE) 2026. Create a reading module about: {topic}.\n"
    
    if format_choice == "1":
        specifics = "1. TEXT: Write a semi-academic text of 300-400 words.\n2. QUESTIONS: 4 questions (Main Idea, Inference, Relationship, Vocabulary). Randomize the question stems."
    elif format_choice == "2":
        specifics = "1. TEXT: Write TWO separate passages (A and B), 200 words each.\n2. QUESTIONS: 4 questions (Synthesis, Cross-Text Agreement, Authorial Response, Differential Inference)."
    elif format_choice == "3":
        specifics = "1. TEXT: Format as a digital forum thread. YOU MUST FORMAT THE THREAD AS A STRICT MARKDOWN TABLE with two columns: 'User' and 'Post Content'. Include User1 and 5 distinct replies.\n2. QUESTIONS: 4 questions (Debate Trajectory, User Alignment, Logical Evaluation, Intent/Tone)."
    elif format_choice == "4":
        specifics = "1. TEXT: Write a scientific text (300 words) with specific data/percentages.\n2. QUESTIONS: 4 questions (Quantitative Inference, Data Interpretation, Main Idea, Flaw)."
    else: 
        specifics = "1. TEXT: Write an analytical Soshum text (300-400 words) focusing on sociology or history.\n2. QUESTIONS: 4 questions (Author's Tone, Societal Inference, Argumentative Structure, Social Causality)."
        
    json_rules = f"\nCRITICAL OUTPUT FORMAT: Output strictly in JSON format matching this schema:\n{JSON_SCHEMA}" 
    return base_intro + specifics + UNIVERSAL_CONSTRAINTS + json_rules

# --- VISUAL FRONTEND ---
st.title("🎓 Interactive UTBK LBE 2026")

with st.sidebar:
    st.header("🔑 Authentication")
    user_api_key = st.text_input("Enter your Gemini API Key:", type="password", placeholder="Paste your key here...")
    
    with st.expander("❓ How to get a FREE API key"):
        st.markdown("**It takes 30 seconds and is completely free:**\n1. Go to [Google AI Studio](https://aistudio.google.com/app/apikey).\n2. Sign in with your Google Account.\n3. Click **Create API key**.\n4. Copy and paste it above.")
        
    st.divider()
    
    st.header("⚙️ Generator Settings")
    format_choice = st.selectbox("Select Format:", ["1. Standard Text", "2. Dual Passages", "3. Digital Thread (Table)", "4. Quantitative/Saintek", "5. Soshum"])
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
                
                with st.spinner("Generating interactive quiz..."):
                    client = genai.Client(api_key=user_api_key) 
                    format_num = format_choice.split(".")[0]
                    
                    # THE TOPIC RANDOMIZER
                    if user_topic.strip():
                        final_topic = user_topic.strip()
                    else:
                        diverse_topics = ["modern pop culture and social media", "economics and bizarre business trends", "sports history or e-sports", "arts and music history", "a weird historical event", "urban legends or human behavior", "global food trends", "modern moral dilemmas"]
                        final_topic = random.choice(diverse_topics)
                    
                    prompt = get_prompt_template(format_num, final_topic)
                    
                    try:
                        # NATIVE JSON FORCING: This makes the API physically incapable of outputting broken formatting.
                        response = client.models.generate_content(
                            model='gemini-2.5-flash-lite', 
                            contents=prompt,
                            config=types.GenerateContentConfig(
                                response_mime_type="application/json"
                            )
                        )
                        
                        # THE SCRUBBER: Forcibly remove any markdown backticks the AI hallucinates
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

# --- INTERACTIVE QUIZ UI ---
if st.session_state.quiz_data:
    quiz = st.session_state.quiz_data
    
    st.markdown("### Reading Passage")
    st.markdown(quiz.get("text", "Text missing."), unsafe_allow_html=True)
    st.divider()
    
    st.markdown("### Questions")
    user_answers = {}
    
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
            
            if isinstance(correct_index, str):
                clean_char = correct_index.strip().upper().replace('"', '')
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
                st.info(f"**Explanation:** {explanation_text}")
                st.write("---")
            
        st.subheader(f"Final Score: {score} / 4")
        if st.button("Reset Quiz"):
            st.session_state.submitted = False
            st.rerun()
