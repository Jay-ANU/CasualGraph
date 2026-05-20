import openai
import os
import json
import re
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import asyncio
from config import Config
import nltk
from nltk.corpus import stopwords
from nltk.tokenize import sent_tokenize, word_tokenize
from nltk.tag import pos_tag
from nltk.stem import WordNetLemmatizer
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Download required NLTK data
try:
    nltk.data.find('tokenizers/punkt')
    nltk.data.find('corpora/stopwords')
    nltk.data.find('taggers/averaged_perceptron_tagger')
    nltk.data.find('corpora/wordnet')
except LookupError:
    nltk.download('punkt')
    nltk.download('stopwords')
    nltk.download('averaged_perceptron_tagger')
    nltk.download('wordnet')

@dataclass
class CausalRelationship:
    cause: str
    effect: str
    confidence: float
    evidence: str
    domain: str
    relationship_type: str = "causes"
    cause_char_span: Optional[Tuple[int, int]] = None
    effect_char_span: Optional[Tuple[int, int]] = None

class CausalExtractor:
    def __init__(self):
        # Initialize OpenAI client with error handling
        try:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                print("Warning: OPENAI_API_KEY not found in environment variables")
                self.client = None
            else:
                self.client = openai.OpenAI(api_key=api_key)
                print("OpenAI client initialized successfully")
        except Exception as e:
            print(f"Error initializing OpenAI client: {e}")
            self.client = None
        
        # CDK status - will be set by external calls
        self.cdk_status = {"is_activated": False}
        
        # Stopwords set
        self.stopwords = set(stopwords.words('english'))
        self.lemmatizer = WordNetLemmatizer()
        
        # Valid relationship types enumeration
        self.valid_relationship_types = [
            "causes", "prevents", "increases_risk", "reduces", 
            "influences", "defines", "used_for", "part_of"
        ]
        
        # Domain-specific prompts
        self.domain_prompts = {
            "healthcare": """
            You are an expert in healthcare causal analysis. Extract cause-effect relationships from the following text.
            
            STRICT RULES:
            1. Cause and effect MUST be noun phrases (≤7 words), not sentences or verb phrases
            2. NO functional words at start (the, which, should, then, etc.)
            3. Use ONLY these relationship types: causes, prevents, increases_risk, reduces, influences, defines, used_for, part_of
            4. Each relationship MUST include evidence chunk (≤30 words) with character spans
            5. Confidence: 0.7-1.0 for strong evidence, 0.5-0.7 for moderate
            
            Return JSON array with: cause, effect, relationship_type, confidence, evidence, cause_char_span, effect_char_span
            """,
            
            "financial": """
            You are an expert in financial causal analysis. Extract cause-effect relationships from the following text.
            
            STRICT RULES:
            1. Cause and effect MUST be noun phrases (≤7 words), not sentences or verb phrases
            2. NO functional words at start (the, which, should, then, etc.)
            3. Use ONLY these relationship types: causes, prevents, increases_risk, reduces, influences, defines, used_for, part_of
            4. Each relationship MUST include evidence chunk (≤30 words) with character spans
            5. Confidence: 0.7-1.0 for strong evidence, 0.5-0.7 for moderate
            
            Return JSON array with: cause, effect, relationship_type, confidence, evidence, cause_char_span, effect_char_span
            """,
            
            "general": """
            You are an expert in causal analysis. Extract cause-effect relationships from the following text.
            
            STRICT RULES:
            1. Cause and effect MUST be noun phrases (≤7 words), not sentences or verb phrases
            2. NO functional words at start (the, which, should, then, etc.)
            3. Use ONLY these relationship types: causes, prevents, increases_risk, reduces, influences, defines, used_for, part_of
            4. Each relationship MUST include evidence chunk (≤30 words) with character spans
            5. Confidence: 0.7-1.0 for strong evidence, 0.5-0.7 for moderate
            
            Return JSON array with: cause, effect, relationship_type, confidence, evidence, cause_char_span, effect_char_span
            """
        }
        
        # Improved regex patterns - stricter constraints
        self.causal_patterns = [
            # Noun phrase + verb + noun phrase
            r'(\b(?:[A-Z][a-z]+\s+){1,6}(?:[A-Z][a-z]+))\s+(?:causes?|leads?\s+to|results?\s+in|triggers?|induces?)\s+(\b(?:[A-Z][a-z]+\s+){1,6}(?:[A-Z][a-z]+))',
            r'(\b(?:[A-Z][a-z]+\s+){1,6}(?:[A-Z][a-z]+))\s+(?:is\s+caused\s+by|results?\s+from|arises?\s+from)\s+(\b(?:[A-Z][a-z]+\s+){1,6}(?:[A-Z][a-z]+))',
            r'(\b(?:[A-Z][a-z]+\s+){1,6}(?:[A-Z][a-z]+))\s+(?:increases?\s+the\s+risk\s+of|reduces?\s+the\s+chance\s+of)\s+(\b(?:[A-Z][a-z]+\s+){1,6}(?:[A-Z][a-z]+))',
            r'(\b(?:[A-Z][a-z]+\s+){1,6}(?:[A-Z][a-z]+))\s+(?:prevents?|stops?|blocks?)\s+(\b(?:[A-Z][a-z]+\s+){1,6}(?:[A-Z][a-z]+))',
            r'(\b(?:[A-Z][a-z]+\s+){1,6}(?:[A-Z][a-z]+))\s+(?:influences?|affects?|impacts?)\s+(\b(?:[A-Z][a-z]+\s+){1,6}(?:[A-Z][a-z]+))'
        ]

    def set_cdk_status(self, cdk_status: dict):
        """Set the CDK activation status for this extractor"""
        self.cdk_status = cdk_status
        print(f"CDK status set in extractor: {cdk_status}")
    
    def can_use_openai(self) -> bool:
        """Check if OpenAI API can be used based on CDK status"""
        can_use = self.cdk_status.get("is_activated", False) and self.client is not None
        print(f"Can use OpenAI: CDK={self.cdk_status.get('is_activated', False)}, Client={self.client is not None}, Result={can_use}")
        return can_use

    def clean_text_for_extraction(self, text: str) -> str:
        """
        Deep text cleaning: remove PDF line breaks, page numbers, headers and footers
        """
        # Remove page numbers (e.g., "6", "12", "Page 8")
        text = re.sub(r'\b(?:Page\s+)?\d+\b', '', text)
        
        # Remove header/footer identifiers
        text = re.sub(r'\b(?:Header|Footer|Page|Chapter|Section)\s*[:：]\s*\S*', '', text)
        
        # Merge line-broken sentences
        text = re.sub(r'([a-z])\n([A-Z])', r'\1 \2', text)
        
        # Remove excess whitespace
        text = re.sub(r'\s+', ' ', text)
        
        # Remove leading/trailing whitespace
        text = text.strip()
        
        return text

    def is_valid_noun_phrase(self, phrase: str) -> bool:
        """
        Validate if phrase is a valid noun phrase
        """
        if not phrase or len(phrase.strip()) < 3:
            return False
            
        # Check if starts with stopword
        words = phrase.strip().split()
        if words and words[0].lower() in self.stopwords:
            return False
            
        # Check length limit
        if len(words) > 7:
            return False
            
        # Check if contains verb-like content
        pos_tags = pos_tag(words)
        has_noun = any(tag.startswith('NN') for word, tag in pos_tags)
        
        return has_noun

    async def extract_relationships(self, text: str, domain: str = "general") -> List[CausalRelationship]:
        """
        Extract causal relationships using CDK-aware model selection
        """
        # Deep text cleaning
        cleaned_text = self.clean_text_for_extraction(text)
        
        # Debug: Print current CDK status
        print(f"Current CDK status in extractor: {self.cdk_status}")
        print(f"Can use OpenAI: {self.can_use_openai()}")
        print(f"OpenAI client available: {self.client is not None}")
        
        # Check if we can use OpenAI based on CDK status
        if self.can_use_openai():
            try:
                print("Using OpenAI GPT-4 for causal extraction (CDK activated)")
                # Use GPT extraction
                relationships = await self._extract_with_gpt(cleaned_text, domain)
                
                # Validate and filter relationships
                valid_relationships = []
                for rel in relationships:
                    if self.is_valid_noun_phrase(rel.cause) and self.is_valid_noun_phrase(rel.effect):
                        valid_relationships.append(rel)
                
                # If GPT extraction fails or quality is low, use improved pattern matching
                if len(valid_relationships) < 3:
                    print("GPT extraction quality low, supplementing with pattern matching")
                    pattern_relationships = self._extract_with_patterns(cleaned_text, domain)
                    valid_relationships.extend(pattern_relationships)
                
                return valid_relationships
                
            except Exception as e:
                print(f"Error in GPT extraction: {e}, falling back to pattern matching")
                # Fallback to pattern matching
                return self._extract_with_patterns(cleaned_text, domain)
        else:
            print("Using local pattern matching for causal extraction (CDK not activated)")
            # Use only local pattern matching
            return self._extract_with_patterns(cleaned_text, domain)

    async def _extract_with_gpt(self, text: str, domain: str) -> List[CausalRelationship]:
        """
        Extract causal relationships using GPT with hard constraints
        """
        # Check if OpenAI client is available
        if not self.client:
            print("OpenAI client not available, skipping GPT extraction")
            return []

        try:
            system_message = self.domain_prompts.get(domain, self.domain_prompts["general"])

            user_message = f"""
            Extract causal relationships from this text following the STRICT RULES:

            {text}

            Return ONLY valid relationships with proper noun phrases and evidence chunks.
            """

            response = await asyncio.to_thread(
                self.client.chat.completions.create,
                model=Config.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": user_message}
                ],
                temperature=Config.OPENAI_TEMPERATURE,
                max_tokens=Config.OPENAI_MAX_TOKENS
            )

            content = response.choices[0].message.content.strip()
            
            # Parse JSON response
            try:
                json_match = re.search(r'\[.*\]', content, re.DOTALL)
                if json_match:
                    json_str = json_match.group(0)
                    relationships_data = json.loads(json_str)
                    
                    relationships = []
                    for rel_data in relationships_data:
                        # Validate relationship type
                        rel_type = rel_data.get("relationship_type", "causes")
                        if rel_type not in self.valid_relationship_types:
                            rel_type = "causes"  # Default value
                        
                        # Validate confidence
                        confidence = float(rel_data.get("confidence", 0.7))
                        confidence = max(0.5, min(1.0, confidence))  # Limit to 0.5-1.0
                        
                        rel = CausalRelationship(
                            cause=rel_data.get("cause", ""),
                            effect=rel_data.get("effect", ""),
                            confidence=confidence,
                            evidence=rel_data.get("evidence", ""),
                            domain=domain,
                            relationship_type=rel_type,
                            cause_char_span=rel_data.get("cause_char_span"),
                            effect_char_span=rel_data.get("effect_char_span")
                        )
                        relationships.append(rel)
                    
                    return relationships
                    
            except json.JSONDecodeError as e:
                print(f"JSON parsing error: {e}")
                return []
                
        except Exception as e:
            print(f"GPT API error: {e}")
            return []

    def _extract_with_patterns(self, text: str, domain: str) -> List[CausalRelationship]:
        """
        Extract causal relationships using improved pattern matching
        """
        relationships = []
        sentences = sent_tokenize(text)
        
        for sentence in sentences:
            for pattern in self.causal_patterns:
                matches = re.finditer(pattern, sentence, re.IGNORECASE)
                
                for match in matches:
                    cause = match.group(1).strip()
                    effect = match.group(2).strip()
                    
                    # Validate noun phrases
                    if self.is_valid_noun_phrase(cause) and self.is_valid_noun_phrase(effect):
                        # Find evidence chunk
                        start = max(0, match.start() - 15)
                        end = min(len(sentence), match.end() + 15)
                        evidence = sentence[start:end].strip()
                        
                        rel = CausalRelationship(
                            cause=cause,
                            effect=effect,
                            confidence=0.6,  # Lower confidence for pattern matching
                            evidence=evidence,
                            domain=domain,
                            relationship_type="causes"
                        )
                        relationships.append(rel)
        
        return relationships
