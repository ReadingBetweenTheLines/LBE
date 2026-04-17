import streamlit as st
import os
import json
import time
import re
from google import genai
from dotenv import load_dotenv

# --- CONFIGURATION & SECURITY ---
st.set_page_config(page_title="LBE UTBK 2026 Quiz", page_icon="🎓", layout="wide")
load_dotenv()

# --- SESSION STATE INITIALIZATION ---
# Streamlit refreshes the page on every click. We need memory to remember the quiz.
if "quiz_data" not in st.session_state:
    st.session_state.quiz_data = None
if "submitted" not in st.session_state:
    st.session_state.submitted = False
if "last_request_time" not in st.session_state:
    st.session_state.last_request_time = 0

# --- THE ENGINE ROOM (Lite-Model Overdrive) ---
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
        
    json_rules = f"""
    CRITICAL OUTPUT FORMAT: You MUST output the entire response as a raw JSON object matching this exact schema. 
    DO NOT wrap it in markdown code blocks (no ```json). 
    CRITICAL JSON RULE: You MUST properly escape all internal quotation marks (e.g., \\"word\\") and use \\n for line breaks inside strings.
    {JSON_SCHEMA}
    """ 
    return base_intro + specifics + UNIVERSAL_CONSTRAINTS + json_rules

# --- VISUAL FRONTEND ---
st.title("🎓 Interactive UTBK LBE 2026")

# Generator UI & BYOK Authentication
with st.sidebar:
    st.header("🔑 Authentication")
    
    # The Secure Input Field
    user_api_key = st.text_input(
        "Enter your Gemini API Key:", 
        type="password", 
        placeholder="Paste your key here..."
    )
    
    # The Built-in Tutorial for Students
    with st.expander("❓ How to get a FREE API key"):
        st.markdown("""
        **It takes 30 seconds and is completely free:**
        1. Go to [Google AI Studio](https://aistudio.google.com/app/apikey).
        2. Sign in with your Google Account.
        3. Click the blue **Create API key** button.
        4. Copy the long string of text and paste it into the box above.
        
        *Your key is safe. It is never saved, stored, or logged by this website. It is wiped the moment you close this tab.*
        """)
        
    st.divider()
    
    st.header("⚙️ Generator Settings")
    format_choice = st.selectbox(
        "Select Format:",
        ["1. Standard Text", "2. Dual Passages", "3. Digital Thread (Table)", "4. Quantitative/Saintek", "5. Soshum"]
    )
    user_topic = st.text_input("Topic:", placeholder="Leave blank for random...")
    
    if st.button("🚀 Generate Quiz", type="primary", use_container_width=True):
        if not user_api_key:
            st.error("⚠️ Please enter your Gemini API Key at the top of the sidebar first!")
        elif len(user_api_key) < 35:
            st.warning("⚠️ That doesn't look like a valid Google API key. It should be longer.")
        else:
            current_time = time.time()
            time_since_last = current_time - st.session_state.last_request_time
            
            if time_since_last < 60:
                wait_time = int(60 - time_since_last)
                st.warning(f"⏳ API Cooldown Active. Please wait {wait_time} seconds.")
            else:
                st.session_state.last_request_time = current_time
                
                with st.spinner("Generating interactive quiz..."):
                    # Use the USER'S key
                    client = genai.Client(api_key=user_api_key) 
                    format_num = format_choice.split(".")[0]
                    final_topic = user_topic.strip() or "a completely random, highly niche UTBK topic."
                    
                    prompt = get_prompt_template(format_num, final_topic)
                    
                    try:
                        response = client.models.generate_content(model='gemini-2.5-flash-lite', contents=prompt)
                        raw_text = response.text
                            
                        # THE CLEANER: Hunt down the JSON block even if the AI added conversational filler
                        match = re.search(r'\{.*\}', raw_text, re.DOTALL)
                            
                        if match:
                            clean_json = match.group(0)
                            # Fix common Lite-model formatting mistakes before parsing
                            clean_json = clean_json.replace("```json", "").replace("```", "").strip()
                                
                            st.session_state.quiz_data = json.loads(clean_json)
                            st.session_state.submitted = False
                        else:
                            st.error("The AI did not return a recognizable JSON format. Please click generate again.")
                            # Prints the raw broken text to the terminal so you can debug what the AI actually said
                            print("BROKEN AI OUTPUT:\n", raw_text) 
                                
                    except json.JSONDecodeError as e:
                        st.error("The AI made a syntax error while formatting the JSON. Click generate again.")
                        print(f"JSON ERROR: {e}\nRAW TEXT:\n{clean_json}")
                    except Exception as e:
                        error_msg = str(e)
                        if "429" in error_msg:
                            st.warning("🚦 The server is currently too busy! We hit our 1-minute speed limit. Please wait 15 seconds and try again.")
                        else:
                            st.error(f"Generation Error: {e}")

# --- INTERACTIVE QUIZ UI ---
if st.session_state.quiz_data:
    quiz = st.session_state.quiz_data
    
    # 1. Display the Text (It will automatically render tables if Format 3 was chosen)
    st.markdown("### Reading Passage")
    st.markdown(quiz["text"], unsafe_allow_html=True)
    st.divider()
    
    # 2. Display the Questions interactively
    st.markdown("### Questions")
    
    # We create a dictionary to store the user's selected answers
    user_answers = {}
    
    for i, q in enumerate(quiz["questions"]):
        st.markdown(f"**{i+1}. {q['question_stem']}**")
        
        # Create radio buttons for options
        user_answers[i] = st.radio(
            f"Select answer for question {i+1}", 
            options=q["options"], 
            key=f"q_{i}",
            label_visibility="collapsed"
        )
        st.write("") # Add spacing
    
    # 3. The Submit Button
    if not st.session_state.submitted:
        if st.button("Submit Answers", type="primary"):
            st.session_state.submitted = True
            st.rerun() # Refresh the page to show results

    # 4. Show Explanations ONLY if submitted
    if st.session_state.submitted:
        st.divider()
        st.markdown("### 📊 Results & Explanations")
        
        score = 0
        for i, q in enumerate(quiz["questions"]):
            # THE SHIELD: Safely look for the index. If missing, look for alternatives.
            correct_index = q.get("correct_answer_index", q.get("correct_answer", q.get("answer", 0)))
            
            # If the AI accidentally output a letter (like "C") instead of a number (like 2)
            if isinstance(correct_index, str):
                letter_map = {"A": 0, "B": 1, "C": 2, "D": 3, "E": 4}
                clean_char = correct_index.strip().upper().replace('"', '')
                correct_index = letter_map.get(clean_char, 0) # Default to 0 if it completely hallucinated
            
            # Ensure it is a valid integer between 0 and 4 so it doesn't crash the list
            try:
                correct_index = int(correct_index)
                if correct_index < 0 or correct_index > 4:
                    correct_index = 0
            except ValueError:
                correct_index = 0

            # Now safely grab the text
            correct_text = q["options"][correct_index]
            user_text = user_answers[i]
            
            if user_text == correct_text:
                score += 1
                st.success(f"**Question {i+1}: Correct!**")
            else:
                st.error(f"**Question {i+1}: Incorrect.** \n\nYou chose: {user_text} \n\nCorrect answer: {correct_text}")
            
            # Safely grab the explanation just in case it renamed that too
            explanation_text = q.get("explanation", q.get("trap_planning", "No explanation provided by AI."))
            st.info(f"**Explanation:** {explanation_text}")
            st.write("---")
            
        st.subheader(f"Final Score: {score} / 4")
        
        if st.button("Reset Quiz"):
            st.session_state.submitted = False
            st.rerun()
