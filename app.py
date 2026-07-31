import os
import json
import streamlit as st
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

# 1. 網頁版面設定
st.set_page_config(page_title="1957-1976 歷史文字RPG", layout="centered")
st.title("📜 第二人生：歷史的齒輪")

# 2. 側邊欄讓玩家輸入 API Key
st.sidebar.header("🔑 系統設定")
api_key_input = st.sidebar.text_input("請輸入你的 Google AI Studio API Key", type="password")

if not api_key_input:
    st.warning("請先在左側欄位輸入您的 API Key 才能啟動遊戲。")
    st.stop()

# 初始化 Gemini 客戶端
client = genai.Client(api_key=api_key_input)

# 3. 定義 AI 結構化輸出格式
class StatChanges(BaseModel):
    health_change: int = Field(description="肉體枯竭度變動值 (-30 到 +10)")
    sanity_change: int = Field(description="雙重思想度變動值 (-30 到 +20)")
    complicity_change: int = Field(description="共業/沾血度變動值 (0 到 +30)")

class NPCUpdate(BaseModel):
    name: str
    affinity_change: int
    moral_alignment_change: int
    status: str

class NPCUpdates(BaseModel):
    oppressor: NPCUpdate
    dependent: NPCUpdate
    ally: NPCUpdate

class GameResponse(BaseModel):
    story_text: str 
    option_A: str 
    option_B: str 
    option_C: str 
    stat_changes: StatChanges
    sensory_tags_used: list[str]
    npc_updates: NPCUpdates

# 4. 初始化遊戲狀態（如果玩家剛進網頁）
if "player_state" not in st.session_state:
    st.session_state.player_state = {
        "background": {
            "location": "上海市",
            "ethnicity": "漢族",
            "origin": "右派分子",
            "profession": "街道生產組臨時工",
            "assets": ["打補丁的舊衣服", "幾張全國糧票"]
        },
        "hidden_stats": {"health": 80, "sanity": 70, "complicity": 0},
        "current_year": 1957,
        "game_stage": "prologue",
        "npc_roster": {
            "oppressor": {"name": "未設定", "affinity": 30, "moral_alignment": 20, "status": "alive"},
            "dependent": {"name": "未設定", "affinity": 80, "moral_alignment": 80, "status": "alive"},
            "ally": {"name": "未結識", "affinity": 60, "moral_alignment": 50, "status": "alive"}
        }
    }
    st.session_state.used_tropes = {"forbidden_sensory": []}
    st.session_state.current_output = None
    st.session_state.game_over = False

# 載入靜態資料庫
@st.cache_data
def load_databases():
    with open('historical_timeline.json', 'r', encoding='utf-8') as f:
        timeline = json.load(f)
    with open('taboo_dictionary.json', 'r', encoding='utf-8') as f:
        taboo = json.load(f)
    return timeline, taboo

timeline, taboo = load_databases()

# 5. 遊戲回合驅動函數
def run_turn(choice_text=""):
    p_state = st.session_state.player_state
    
    if p_state["hidden_stats"]["health"] <= 0:
        st.session_state.game_over = "【肉體枯竭】你在無盡的飢餓與肉體折磨中倒下，未能熬過這個時代。"
        return
    if p_state["current_year"] > 1976:
        st.session_state.game_over = "【時代落幕】1976年，狂飆的歷史終於停息，你活著見證了結束。"
        return

    year = str(p_state["current_year"])
    historical_fact = timeline.get(year, timeline["1957"])
    
    system_instruction = f"""
    你是一位頂級文字RPG導演。請嚴格遵守以下時代禁忌詞彙對照表：
    {json.dumps(taboo, ensure_ascii=False)}
    絕對禁止使用宏觀歷史定性名詞。客觀化感官拆解，提供3個純物理動作選項。
    """
    
    prompt = f"""
    【目前歷史齒輪】：{json.dumps(historical_fact, ensure_ascii=False)}
    【玩家背景】：{json.dumps(p_state["background"], ensure_ascii=False)}
    【玩家狀態】：{json.dumps(p_state["hidden_stats"], ensure_ascii=False)}
    【上一步抉擇】：{choice_text if choice_text else "歷史開局，序章啟動。"}
    請生成故事、選項與狀態更新。
    """
    
    with st.spinner("⏳ 歷史的齒輪正在運轉，AI 正在生成故事..."):
        response = client.models.generate_content(
            model='gemini-3.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
                response_schema=GameResponse,
                temperature=0.75,
            ),
        )
        
        output = json.loads(response.text)
        st.session_state.current_output = output
        
        # 更新數值
        changes = output["stat_changes"]
        p_state["hidden_stats"]["health"] = max(0, min(100, p_state["hidden_stats"]["health"] + changes["health_change"]))
        p_state["hidden_stats"]["sanity"] = max(0, min(100, p_state["hidden_stats"]["sanity"] + changes["sanity_change"]))
        p_state["hidden_stats"]["complicity"] = max(0, min(100, p_state["hidden_stats"]["complicity"] + changes["complicity_change"]))
        
        # 更新年份
        if p_state["game_stage"] == "prologue":
            p_state["current_year"] = 1958
            p_state["game_stage"] = "main_flow"
        else:
            p_state["current_year"] += 1

# 6. 網頁介面呈現
if st.session_state.game_over:
    st.error(st.session_state.game_over)
    st.stop()

# 首次進入自動執行序章
if st.session_state.current_output is None:
    run_turn()
    st.rerun()

# 顯示當前年份與狀態提示
p_state = st.session_state.player_state
st.markdown(f"### 📍 當前年份：{p_state['current_year']} 年")

# 顯示 UI 異變警告
h, s, c = p_state["hidden_stats"]["health"], p_state["hidden_stats"]["sanity"], p_state["hidden_stats"]["complicity"]
if h <= 40: st.warning("⚠️ 【視覺異變】螢幕邊緣出現暗角，畫面褪為灰白，文字明暗閃爍...")
if s <= 35: st.warning("⚠️ 【視覺異變】排版錯位失調，關鍵名詞閃爍為血紅色...")
if c >= 40: st.error("⚠️ 【視覺異變】螢幕底層滲出暗褐色墨暈印記，無法洗刷...")

# 顯示故事文本
output = st.session_state.current_output
st.markdown("---")
st.write(output["story_text"])
st.markdown("---")

# 顯示選項按鈕
st.subheader("🤔 你的物理抉擇：")
if st.button(output["option_A"]):
    run_turn(output["option_A"])
    st.rerun()
if st.button(output["option_B"]):
    run_turn(output["option_B"])
    st.rerun()
if st.button(output["option_C"]):
    run_turn(output["option_C"])
    st.rerun()
