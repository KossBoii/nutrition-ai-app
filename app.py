import os
import re
import tempfile
from dotenv import load_dotenv

import numpy as np
import gradio as gr
from PIL import Image
import json
from io import BytesIO

import google.generativeai as genai
from google.genai import types, Client

def convert_dict_to_string(data: dict) -> str:
    assert isinstance(data, dict)
    pretty_json = json.dumps(data, indent=4)    
    return pretty_json

def postprocess_response(response):
    # Post-process the response to extract the relevant information
    try:
        # Regular expression to match JSON blocks starting with ```json and ending with ```
        json_pattern = r"```json\s*(\{(?:.|\n)*?\})\s*```"
        matches = re.findall(json_pattern, response)

        # Parse each match as JSON
        extracted_jsons = []
        for match in matches:
            try:
                json_data = json.loads(match)  # Parse as JSON
                extracted_jsons.append(json_data)
            except json.JSONDecodeError as e:
                print(f"Invalid JSON found: {e}")
        return extracted_jsons
    except Exception as e:
        print(f"Error during extraction: {e}")
        raise e

def process_request(image, prompt):
    try:

        # Convert ndarray to image file if necessary
        if isinstance(image, np.ndarray):
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
                temp_image = Image.fromarray(image)
                temp_image.save(temp_file.name)
                image_path = temp_file.name
        else:
            image_path = image  # Assume it's already a file path

        prompt_parts = [
            genai.upload_file(image_path),
            prompt,
        ]
        
        response = model.generate_content(prompt_parts)
        return  postprocess_response(response.text)[0]  # Return the first JSON object
    except Exception as e:
        print(f"Error: {e}")
        return "An error occurred while processing the request."

def generate_fda_label(json_data: dict) -> np.ndarray:
    # Placeholder function to generate an FDA-style label image
    json_data_str = convert_dict_to_string(json_data)
    prompt = f"""
        Generate a high-quality, FDA-style nutrition label image using the following structured data. 
        Ensure the label includes all key sections such as serving size, calories, macronutrients, micronutrients, and ingredient list, 
        formatted clearly and legibly for human reading. Use proper FDA label fonts and layout, with clean black-and-white contrast 
        and clear separation between sections. \n
        Data:\n
        {json_data_str}     
        Note: Clearly display the following information in the label:
            - Serving Size
            - Calories
            - Macronutrients (Protein, Carbohydrates, Fats, Fiber, Sugar, Saturated Fat, Unsaturated Fat)
            - Micronutrients (Vitamins A, C, D, E, K, Calcium, Iron, Magnesium, Potassium, Zinc, Sodium)
            - Ingredient List
            - Meal Type (Breakfast, Lunch, Dinner, Snack)
        Format the label to mimic official FDA packaging standards, using aligned tables or sections and readable numeric values. 
        Make sure text is sharp, aligned, and not blurry.
    """
    response = client.models.generate_content(
        model='gemini-2.0-flash-exp-image-generation',
        contents=prompt,
        config=types.GenerateContentConfig(
            response_modalities=['TEXT', 'IMAGE']
        )
    )
    
    for part in response.candidates[0].content.parts:
        if part.text is not None:
            print(part.text)
        elif part.inline_data is not None:
            image = Image.open(BytesIO((part.inline_data.data)))
            image_array = np.array(image)

            return image_array
    
def get_prompt_options():
    # Placeholder function to get prompt options
    return [
        """You are an expert nutritionist. Analyze the image and provide a detailed report on the nutritional content of the food items in the image.
            Automatically identify and extract the data, then organize it into the following structured JSON format:
            {
                "ingredients": ["ingredient1", "ingredient2", "..."],
                "nutritional_values": {
                    "calories": "X calories",
                    "protein": "X grams",
                    "carbohydrates": "X grams",
                    "fats": "X grams",
                    "macro_nutrients": {
                        "fiber": "X grams",
                        "sugar": "X grams",
                        "saturated_fat": "X grams",
                        "unsaturated_fat": "X grams"
                    },
                    "micro_nutrients": {
                        "vitamin_a": "X IU",
                        "vitamin_c": "X mg",
                        "vitamin_d": "X IU",
                        "vitamin_e": "X mg",
                        "vitamin_k": "X mcg",
                        "calcium": "X mg",
                        "iron": "X mg",
                        "magnesium": "X mg",
                        "potassium": "X mg",
                        "zinc": "X mg",
                        "sodium": "X mg"
                    }
                },
                "serving_size": "X grams",
                "meal_type": "breakfast/lunch/dinner/snack"
            }
            Ensure the values are as accurate as possible based on the visual and contextual information from the image.
        """,
    ]


def process_nutrition_facts(image, prompt) -> str:
    if image is None or prompt is None:
        return "Please upload an image and select/enter a prompt.", None
    
    result = process_request(image, prompt)
    if isinstance(result, dict):
        pretty_json = json.dumps(result, indent=4)
        print("Returning JSON data")
        return pretty_json, result
    return f"{result}", {}

def generate_label(nutrition_facts_data: dict) -> np.ndarray:
    if nutrition_facts_data is None:
        print("No nutrition facts data provided.")
        return None
    fda_label = generate_fda_label(nutrition_facts_data)
    return fda_label


if __name__ == "__main__":
    # Load environment variables from .env file
    load_dotenv()
    
    # Set the API key for Google Generative AI
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    model = genai.GenerativeModel(model_name=os.getenv("MODEL_NAME"))
    client = Client(api_key=os.getenv("GEMINI_API_KEY"))
    
    # Create Gradio interface
    with gr.Blocks() as demo:
        gr.Markdown("## Upload an Image for Processing")
        file_input = gr.Image(label="Upload your image")  # Changed to image upload

        gr.Markdown("## Select or Enter a Prompt")
        prompt_dropdown = gr.Dropdown(
            choices=get_prompt_options(), 
            label="Select a pre-loaded prompt"
        )
        final_output = gr.Textbox(label="Final Output")  # Use this for all outputs
        fda_label_output = gr.Image(label="FDA Label Output")  # New image output for FDA label

        # Add a process button to handle image and prompt together
        process_button = gr.Button("Process")

        nutrition_facts = gr.State()
        process_button.click(
            process_nutrition_facts,
            inputs=[file_input, prompt_dropdown],
            outputs=[final_output, nutrition_facts]
        ).then(
            generate_label,
            inputs=[nutrition_facts],  # Use the raw_result from the previous step
            outputs=fda_label_output  # Only updates the FDA label when ready
        )
    
    # Launch the Gradio app
    demo.launch()
