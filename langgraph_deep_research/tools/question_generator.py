"""
Question Generator Tool using Novita AI (Qwen 3.5 397B model).

This tool generates focused research questions from a given topic using
OpenAI-compatible API via Novita AI.
"""

import json
import logging
import sys
from pathlib import Path
from typing import List, Optional
from openai import OpenAI

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import Config

logger = logging.getLogger(__name__)


class QuestionGenerator:
    """
    Generates research questions using Novita AI's Qwen 3.5 397B model.
    
    This tool takes a research topic and generates 3-5 specific, focused
    research questions that cover different aspects of the topic.
    """

    def __init__(self):
        """Initialize the Question Generator with Novita AI configuration."""
        Config.validate()
        novita_config = Config.get_novita_config()
        
        self.client = OpenAI(
            api_key=novita_config["api_key"],
            base_url=novita_config["base_url"]
        )
        self.model = novita_config["model"]
        self.temperature = novita_config["temperature"]
        self.max_tokens = novita_config["max_tokens"]
        
        logger.info(f"Initialized QuestionGenerator with model: {self.model}")

    def generate_questions(self, topic: str, num_questions: Optional[int] = None) -> List[str]:
        """
        Generate research questions for a given topic.
        
        Args:
            topic: The research topic to generate questions for
            num_questions: Number of questions to generate (default: 3-5)
            
        Returns:
            List of research questions as strings
            
        Raises:
            ValueError: If topic is empty or questions cannot be generated
            Exception: If API call fails
        """
        if not topic or not topic.strip():
            raise ValueError("Topic cannot be empty")
        
        if num_questions is None:
            num_questions = Config.MAX_QUESTIONS
        
        num_questions = max(Config.MIN_QUESTIONS, min(num_questions, Config.MAX_QUESTIONS))
        
        logger.info(f"Generating {num_questions} research questions for topic: {topic}")
        
        system_prompt = """You are an expert research assistant. Your task is to generate specific, 
focused research questions that will enable comprehensive investigation of a given topic.

Generate questions that:
1. Cover different aspects and angles of the topic
2. Are specific and actionable (not too broad)
3. Are complementary (don't overlap significantly)
4. Will yield valuable insights when researched
5. Are suitable for academic or professional research

Return ONLY a JSON array of question strings, nothing else."""

        user_prompt = f"""Generate {num_questions} focused research questions about: {topic}

Return your response as a JSON array of strings. Example format:
["Question 1?", "Question 2?", "Question 3?"]"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens
            )
            
            content = response.choices[0].message.content.strip()
            logger.debug(f"Raw response from model: {content}")
            
            # Try to extract JSON from the response
            questions = self._parse_questions(content)
            
            if not questions:
                raise ValueError("No valid questions extracted from response")
            
            logger.info(f"Successfully generated {len(questions)} questions")
            return questions
            
        except Exception as e:
            logger.error(f"Error generating questions: {str(e)}")
            raise

    def _parse_questions(self, content: str) -> List[str]:
        """
        Parse questions from model response.
        
        Handles various response formats and extracts the JSON array.
        
        Args:
            content: Raw content from the model
            
        Returns:
            List of question strings
        """
        # Try direct JSON parsing
        try:
            questions = json.loads(content)
            if isinstance(questions, list) and all(isinstance(q, str) for q in questions):
                return [q.strip() for q in questions if q.strip()]
        except json.JSONDecodeError:
            pass
        
        # Try to find JSON array in the content
        import re
        json_match = re.search(r'\[.*?\]', content, re.DOTALL)
        if json_match:
            try:
                questions = json.loads(json_match.group())
                if isinstance(questions, list) and all(isinstance(q, str) for q in questions):
                    return [q.strip() for q in questions if q.strip()]
            except json.JSONDecodeError:
                pass
        
        # Fallback: split by newlines and filter
        lines = [line.strip() for line in content.split('\n') if line.strip()]
        questions = []
        for line in lines:
            # Remove common prefixes like "1.", "- ", etc.
            line = re.sub(r'^[\d\.\-\*\)]+\s*', '', line)
            if line and len(line) > 10:  # Reasonable minimum length
                questions.append(line)
        
        return questions


def generate_research_questions(topic: str, num_questions: Optional[int] = None) -> List[str]:
    """
    Convenience function to generate research questions.
    
    Args:
        topic: The research topic
        num_questions: Optional number of questions (default: 3-5)
        
    Returns:
        List of research questions
    """
    generator = QuestionGenerator()
    return generator.generate_questions(topic, num_questions)
