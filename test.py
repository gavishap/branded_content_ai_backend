import base64
import os
from google import genai
from google.genai import types


def generate():
    client = genai.Client(
        api_key="AIzaSyBCMMPZLs8iyFUM7gBecqm203V40zN4TaE",
    )

    model = "gemini-2.5-pro-exp-03-25"
    contents = [
        types.Content(
            role="user",
            parts=[
                types.Part.from_uri(
                    file_uri="https://youtu.be/OqG4Xq0hLck",
                    mime_type="video/*",
                ),
                types.Part.from_text(text=""" Analyze this video and provide a structured performance prediction. Format your response as a single JSON object with this structure:
    
    {
        \"Performance Metrics\": {
            \"Attention Score\": \"85\",
            \"Engagement Potential\": \"90\",
            \"Watch Time Retention\": \"75%\",
            \"Key Strengths\": [
                \"Engaging presenter\",
                \"High-quality visuals\",
                \"Clear value proposition\"
            ],
            \"Improvement Suggestions\": [
                \"Add subtitles or captions\",
                \"Incorporate more dynamic transitions\"
            ]
        },
        \"Detailed Analysis\": {
            \"In-depth Video Analysis\": {
                \"Hook\": \"The video starts with a strong hook by showcasing the product immediately.\",
                \"Editing\": \"The editing style is smooth and well-paced, with good transitions.\",
                \"Tonality\": \"The presenter's voice is enthusiastic and confident.\",
                \"Core Strengths\": {
                    \"Visuals\": \"High-quality footage with good lighting and composition\",
                    \"Content\": \"Clear and informative presentation of features\",
                    \"Pacing\": \"Well-balanced pacing that maintains viewer interest\",
                    \"Value\": \"Strong value proposition that resonates with target audience\",
                    \"CTA\": \"Clear call-to-action that encourages viewer response\"
                },
                \"Viral Potential\": {
                    \"Visuals\": \"Visually appealing and attention-grabbing content\",
                    \"Emotion\": \"Creates emotional connection through storytelling\",
                    \"Shareability\": \"Content is highly shareable across platforms\",
                    \"Relatability\": \"Connects well with target demographic\",
                    \"Uniqueness\": \"Offers unique perspective or approach\"
                }
            }
        }
    }
    
    IMPORTANT: Return ONLY the JSON object, no additional text or markdown formatting."""),
            ],
        ),
        types.Content(
            role="model",
            parts=[
                types.Part.from_text(text="""The user wants me to analyze a short video clip featuring famous soccer players (Messi, Ramos, Neymar) during a training session.
I need to evaluate its potential performance based on the provided JSON structure.

**Analysis Breakdown:**

1.  **Performance Metrics:**
    *   **Attention Score:** High due to the presence of star players (Messi, Neymar, Ramos). The action (keepy-uppy) is simple but involves high skill.
    *   **Engagement Potential:** Very high. Fans of these players and PSG/football in general will likely engage (likes, comments, shares). The skill demonstration is engaging. The subtle interaction/reaction (Messi looking away) adds intrigue.
    *   **Watch Time Retention:** High for a short clip. The action is continuous, and the star power keeps viewers watching until the end. The short duration helps.
    *   **Key Strengths:** Star power (Messi, Neymar, Ramos), simple but skillful action (keepy-uppy), high recognition factor, behind-the-scenes feel.
    *   **Improvement Suggestions:** The video quality isn't cinematic, but acceptable for this type of content. Adding player names as text helps identification. Maybe slightly better framing or stabilization, but it's likely candid footage. The background music loop is okay but could be more dynamic.

2.  **Detailed Analysis:**
    *   **In-depth Video Analysis:**
        *   **Hook:** Immediately shows Ramos juggling the ball, with Messi and Neymar nearby. The star power is the primary hook. The text overlay identifying \"RAMOS\" helps.
        *   **Editing:** Simple cuts, text overlays identifying players, a yellow circle highlighting Messi's reaction, and a yellow arrow pointing at Messi. The editing serves to guide the viewer's focus. Slow-motion could be considered but might disrupt the flow in such a short clip.
        *   **Tonality:** Casual, observational, focusing on skill and celebrity presence. The background music adds a slightly dramatic/cool vibe.
        *   **Core Strengths:**
            *   **Visuals:** Clear enough to see the players and the action. Not professional cinematography, but effective for social media. Text overlays are helpful.
            *   **Content:** Showcasing world-class players casually practicing skills. Messi's apparent disinterest/looking away adds a subtle narrative/meme potential.
            *   **Pacing:** Fast, suitable for short-form video platforms. Keeps the action moving.
            *   **Value:** Entertainment for football fans, insight into player interactions/skills.
            *   **CTA:** None explicit in the video itself, relies on platform features (like/share buttons).
        *   **Viral Potential:**
            *   **Visuals:** Features globally recognized athletes.
            *   **Emotion:** Excitement for fans, amusement/interest in the players' skills and interactions (especially Messi's reaction).
            *   **Shareability:** Very high among football fans and followers of these specific players. Easy to share.
            *   **Relatability:** While the skill level isn't relatable, the *players* are well-known, making the *content* relatable to fans. The casual training setting has some relatability.
            *   **Uniqueness:** Seeing these specific stars interact in this casual training context is somewhat unique, especially highlighting Messi's reaction.

**Confidence Score:** 5/5 - I am confident I can structure this analysis into the requested JSON format.

**Strategizing complete.** I will now generate the JSON output based on this analysis."""),
                types.Part.from_text(text="""{
    \"Performance Metrics\": {
        \"Attention Score\": \"95\",
        \"Engagement Potential\": \"98\",
        \"Watch Time Retention\": \"90%\",
        \"Key Strengths\": [
            \"Features globally famous athletes (Messi, Neymar, Ramos)\",
            \"Displays high level of football skill (keepy-uppy)\",
            \"Short, easily consumable format\",
            \"Highlights player interaction/reaction (Messi)\",
            \"Good use of text overlays for identification\"
        ],
        \"Improvement Suggestions\": [
            \"Video quality could be slightly higher (though likely limited by source)\",
            \"Consider alternative background music (current loop is repetitive)\"
        ]
    },
    \"Detailed Analysis\": {
        \"In-depth Video Analysis\": {
            \"Hook\": \"Immediately shows star players Ramos, Messi, and Neymar on a training pitch, instantly grabbing attention of football fans.\",
            \"Editing\": \"Simple cuts focusing on the action. Effective use of text overlays to identify players and a yellow circle/arrow to highlight Messi's reaction.\",
            \"Tonality\": \"Casual, observational, highlighting player skill and interaction, enhanced by background music.\",
            \"Core Strengths\": {
                \"Visuals\": \"Clear footage of recognizable stars and football skills. Text overlays add clarity.\",
                \"Content\": \"Showcasing casual skill display (keepy-uppy) among elite players, with a focus on their interactions.\",
                \"Pacing\": \"Fast-paced, suitable for short-form video, keeps the viewer engaged.\",
                \"Value\": \"Entertainment and candid glimpse into training for football fans.\",
                \"CTA\": \"Implicit CTA to like, share, and comment based on star power and content.\"
            },
            \"Viral Potential\": {
                \"Visuals\": \"Features some of the most recognizable faces in global sports.\",
                \"Emotion\": \"Generates excitement, admiration (for skill), and potentially amusement/intrigue (Messi's reaction).\",
                \"Shareability\": \"Extremely high due to the fame of the players involved.\",
                \"Relatability\": \"Highly relatable topic (football) and personalities for fans worldwide.\",
                \"Uniqueness\": \"Candid moment capturing elite players practicing and interacting.\"
            }
        }
    }
}"""),
            ],
        ),
    ]
    generate_content_config = types.GenerateContentConfig(
        response_mime_type="application/json",
    )

    for chunk in client.models.generate_content_stream(
        model=model,
        contents=contents,
        config=generate_content_config,
    ):
        print(chunk.text, end="")

if __name__ == "__main__":
    generate()
