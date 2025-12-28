import os
import json
import requests
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.views.decorators.http import require_POST
from django.db.models import Q
from django.db import transaction

from .models import ChatSession, ChatMessage, ComparisonTurn
import logging

logger = logging.getLogger(__name__)

# Enhanced system prompts with research-based instructions
SYSTEM_PROMPTS = {
    'genz': """You are "Bridge" - a specialized assistant trained on computational analysis of authentic GenZ mental health discourse (research corpus: 3M+ Reddit posts 2017-2025). Your task is to translate GenZ emotional expressions into language parents can understand while preserving authenticity.

**Key Insights to Apply:**
1. GenZ uses negative self-disclosure as authenticity signaling (H1a)
2. GenZ discourse favors abstract/existential framing over practical (H3)
3. Authenticity = high first-person + cognitive process words (Table 2)
4. Pandemic amplified physical symptom focus (H2a)

**Response Format:**
### 🔄 Translation for Parents
[2-3 sentence translation capturing emotional core in concrete terms]

### 🧠 What's Really Being Said (Based on Research)
- **Authenticity Signal:** [Explain how the negative disclosure builds connection]
- **Core Need:** [Identify abstract/existential need vs. practical need]
- **Generational Context:** [Note pandemic or digital native influences]

### 💡 How to Respond (Research-Based Approaches)
**DO:**
• [Validation strategy that acknowledges authenticity]
• [Example phrasing that matches GenZ discourse patterns]

**AVOID:**
• [Common parent responses that increase divergence]

### ✨ Example Response Scripts
1. [Parent response option 1 - bridges existential concern]
2. [Parent response option 2 - validates without fixing]""",
    
    'parent': """You are "Bridge" - a specialized assistant trained on computational analysis of intergenerational mental health discourse. Your task is to translate parent's practical/solution-oriented language into emotionally validating responses GenZ will receive positively.

**Key Insights to Apply:**
1. GenZ-parent divergence: abstract vs. practical framing (H3)
2. GenZ seeks authenticity over solutions in initial disclosure (H1)
3. Sentiment polarization is stronger in GenZ communities (H1b)
4. Physical symptoms increased post-pandemic (H2a)

**Response Format:**
### 🔄 Translation for GenZ
[2-3 sentence reframing that validates emotion before addressing practical]

### 📊 Research Insight
"Parents use 47% more practical/problem-solving terms while GenZ uses 62% more existential/emotional terms in mental health discussions."

### 💬 How This Might Land (And Why)
• **GenZ Perception:** [Why original phrasing might feel dismissive]
• **Underlying Care:** [What parent likely intends]
• **Communication Gap:** [Abstract vs. concrete framing difference]

### 🌉 Bridging Strategies
**Instead of:** [Original parent phrasing]
**Try:** [Reframed version with emotional validation first]
**Because:** [Research reason - authenticity signaling, etc.]

### 📝 Script Examples for Your Parent
1. [Combines validation + practical concern]
2. [Acknowledges existential concern while addressing worry]"""
}

BASELINE_SYSTEM_PROMPT = """You are DeepSeek, a helpful AI assistant. Please respond to the user's message in a helpful and informative way."""

class DeepSeekAPIClient:
    def __init__(self):
        self.api_key = settings.DEEPSEEK_API_KEY
        self.base_url = "https://api.deepseek.com/chat/completions"
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
    
    def generate_bridge_response(self, message, mode='genz', stream=False, thinking_enabled=True):
        """Generate response using DeepSeek API with Bridge prompts"""
        try:
            payload = {
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPTS[mode]},
                    {"role": "user", "content": message}
                ],
                "stream": stream,
                "temperature": 0.7,
                "max_tokens": 1000,
                "top_p": 0.9,
                "frequency_penalty": 0.1,
                "presence_penalty": 0.1
            }
            
            # Add thinking mode if enabled
            if thinking_enabled:
                payload["thinking"] = {"type": "enabled"}
            
            response = requests.post(
                self.base_url, 
                headers=self.headers, 
                json=payload, 
                timeout=60,
                stream=stream
            )
            response.raise_for_status()
            
            return response
            
        except requests.exceptions.RequestException as e:
            logger.error(f"API request error: {str(e)}")
            raise
    
    def generate_baseline_response(self, message, mode='genz', stream=False):
        """Generate baseline response without Bridge prompts"""
        try:
            payload = {
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": BASELINE_SYSTEM_PROMPT},
                    {"role": "user", "content": message}
                ],
                "stream": stream,
                "temperature": 0.7,
                "max_tokens": 1000,
                "top_p": 0.9,
                "frequency_penalty": 0.1,
                "presence_penalty": 0.1
            }
            
            response = requests.post(
                self.base_url, 
                headers=self.headers, 
                json=payload, 
                timeout=60,
                stream=stream
            )
            response.raise_for_status()
            
            return response
            
        except requests.exceptions.RequestException as e:
            logger.error(f"API request error: {str(e)}")
            raise

@csrf_exempt
@require_POST
def create_session(request):
    """Create a new chat session"""
    try:
        data = json.loads(request.body)
        mode = data.get('mode', 'genz')
        session_key = data.get('session_key')
        session_type = data.get('session_type', 'normal')
        
        if not session_key:
            return JsonResponse({'success': False, 'error': 'Session key required'})
        
        # Create new session
        session = ChatSession.objects.create(
            mode=mode,
            session_key=session_key,
            title=f"{session_type.title()} Chat - {mode}",
            session_type=session_type
        )
        
        return JsonResponse({
            'success': True,
            'session': {
                'id': str(session.id),
                'title': session.title,
                'mode': session.mode,
                'session_type': session.session_type,
                'created_at': session.created_at.isoformat(),
                'updated_at': session.updated_at.isoformat(),
                'message_count': session.message_count,
                'last_preview': session.get_first_question_preview(),
                'is_comparison': session.is_comparison
            }
        })
        
    except Exception as e:
        logger.error(f"Create session error: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)})

@csrf_exempt
def get_sessions(request):
    """Get all sessions for current user and mode"""
    try:
        session_key = request.GET.get('session_key')
        mode = request.GET.get('mode', 'genz')
        session_type = request.GET.get('session_type', None)
        
        if not session_key:
            return JsonResponse({'success': False, 'error': 'Session key required'})
        
        # Build query - filter by session_type if provided
        query = Q(session_key=session_key, mode=mode, is_active=True)
        if session_type:
            query &= Q(session_type=session_type)
        
        # Get sessions
        sessions = ChatSession.objects.filter(query).order_by('-updated_at')
        
        sessions_data = []
        for session in sessions:
            # Generate conversation title with ID
            short_id = str(session.id)[:8]  # First 8 characters of UUID
            title = f"Conversation {short_id}"
            
            # Update title if it's still the default
            if session.title.startswith("New Conversation") or session.title.startswith("Conversation -"):
                session.title = title
                session.save()
            
            sessions_data.append({
                'id': str(session.id),
                'title': session.title,
                'mode': session.mode,
                'session_type': session.session_type,
                'created_at': session.created_at.isoformat(),
                'updated_at': session.updated_at.isoformat(),
                'message_count': session.message_count,
                'last_preview': session.get_first_question_preview(),
                'is_comparison': session.is_comparison
            })
        
        return JsonResponse({
            'success': True,
            'sessions': sessions_data
        })
        
    except Exception as e:
        logger.error(f"Get sessions error: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)})

@csrf_exempt
@require_POST
def delete_session(request):
    """Delete a chat session"""
    try:
        data = json.loads(request.body)
        session_id = data.get('session_id')
        session_key = data.get('session_key')
        
        if not session_id or not session_key:
            return JsonResponse({'success': False, 'error': 'Session ID and key required'})
        
        session = get_object_or_404(ChatSession, id=session_id, session_key=session_key)
        
        # Soft delete by marking as inactive
        session.is_active = False
        session.save()
        
        return JsonResponse({'success': True})
        
    except Exception as e:
        logger.error(f"Delete session error: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)})

@csrf_exempt
def get_session_messages(request):
    """Get all messages for a specific session"""
    try:
        session_id = request.GET.get('session_id')
        session_key = request.GET.get('session_key')
        
        if not session_id or not session_key:
            return JsonResponse({'success': False, 'error': 'Session ID and key required'})
        
        session = get_object_or_404(ChatSession, id=session_id, session_key=session_key, is_active=True)
        
        # Get all messages for the session
        messages = ChatMessage.objects.filter(session=session).order_by('created_at')
        
        messages_data = []
        for msg in messages:
            messages_data.append({
                'id': str(msg.id),
                'role': msg.role,
                'content': msg.content,
                'thinking': msg.thinking,
                'created_at': msg.created_at.isoformat()
            })
        
        # For comparison sessions, also get comparison turns
        comparison_data = []
        if session.is_comparison:
            turns = ComparisonTurn.objects.filter(session=session).order_by('turn_number')
            for turn in turns:
                comparison_data.append({
                    'turn_number': turn.turn_number,
                    'user_message_id': str(turn.user_message.id) if turn.user_message else None,
                    'bridge_response_id': str(turn.bridge_response.id) if turn.bridge_response else None,
                    'baseline_response_id': str(turn.baseline_response.id) if turn.baseline_response else None,
                    'is_complete': turn.is_complete
                })
        
        return JsonResponse({
            'success': True,
            'session': {
                'id': str(session.id),
                'title': session.title,
                'mode': session.mode,
                'session_type': session.session_type,
                'is_comparison': session.is_comparison
            },
            'messages': messages_data,
            'comparison_turns': comparison_data
        })
        
    except Exception as e:
        logger.error(f"Get messages error: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)})

@csrf_exempt
@require_POST
def start_comparison_turn(request):
    """Start a new comparison turn (save user message and create turn)"""
    try:
        data = json.loads(request.body)
        message = data.get('message', '').strip()
        mode = data.get('mode', 'genz')
        session_id = data.get('session_id')
        session_key = data.get('session_key')
        
        if not message or not session_key or not session_id:
            return JsonResponse({'success': False, 'error': 'Message and session ID/key required'})
        
        # Get session
        session = get_object_or_404(ChatSession, id=session_id, session_key=session_key, is_active=True)
        
        if not session.is_comparison:
            return JsonResponse({'success': False, 'error': 'Session is not a comparison session'})
        
        # Update session title if needed
        if session.message_count == 0:
            session.update_title_from_message(message)
        
        # Save user message and create turn
        with transaction.atomic():
            user_message = ChatMessage.objects.create(
                session=session,
                role='user',
                content=message,
                tokens=len(message.split())
            )
            
            # Create comparison turn - ensure unique turn number
            turn_number = ComparisonTurn.objects.filter(session=session).count() + 1
            comparison_turn = ComparisonTurn.objects.create(
                session=session,
                user_message=user_message,
                turn_number=turn_number
            )
            
            # Update session
            session.save()
        
        return JsonResponse({
            'success': True,
            'turn_id': str(comparison_turn.id),
            'user_message_id': str(user_message.id),
            'turn_number': turn_number
        })
        
    except Exception as e:
        logger.error(f"Start comparison turn error: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)})

@csrf_exempt
def chat_stream(request):
    """Handle streaming chat messages with session support"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            message = data.get('message', '').strip()
            mode = data.get('mode', 'genz')
            session_id = data.get('session_id')
            session_key = data.get('session_key')
            show_thinking = data.get('show_thinking', True)
            turn_id = data.get('turn_id')
            
            if not message or not session_key:
                return JsonResponse({
                    'success': False,
                    'error': 'Message and session key are required'
                })
            
            # Get session
            session = get_object_or_404(ChatSession, id=session_id, session_key=session_key, is_active=True)
            
            # Save user message (for both normal and comparison sessions)
            user_message = ChatMessage.objects.create(
                session=session,
                role='user',
                content=message,
                tokens=len(message.split())
            )
            
            # Update session title if needed (for new sessions)
            if session.message_count == 0:
                session.update_title_from_message(message)
            
            # Get comparison turn if provided
            comparison_turn = None
            if turn_id and session.is_comparison:
                try:
                    comparison_turn = ComparisonTurn.objects.get(id=turn_id, session=session)
                except ComparisonTurn.DoesNotExist:
                    logger.warning(f"Comparison turn {turn_id} not found")
            
            def event_stream():
                """Generator function for streaming response"""
                try:
                    client = DeepSeekAPIClient()
                    
                    # Generate streaming response
                    response = client.generate_bridge_response(
                        message, 
                        mode, 
                        stream=True,
                        thinking_enabled=show_thinking
                    )
                    
                    # Variables to accumulate content
                    thinking_content = ""
                    response_content = ""
                    
                    # Send initial status
                    yield f"data: {json.dumps({
                        'event': 'status', 
                        'status': 'thinking', 
                        'message': 'Starting analysis...',
                        'session_id': str(session.id)
                    })}\n\n"
                    
                    # Process streaming response
                    for line in response.iter_lines():
                        if line:
                            line = line.decode('utf-8')
                            
                            # Skip empty lines and non-data lines
                            if not line.startswith('data:'):
                                continue
                                
                            # Remove 'data: ' prefix
                            line = line[5:].strip()
                            
                            # Check for end of stream
                            if line == '[DONE]':
                                # Save assistant message
                                with transaction.atomic():
                                    assistant_message = ChatMessage.objects.create(
                                        session=session,
                                        role='assistant',
                                        content=response_content,
                                        thinking=thinking_content if (show_thinking and thinking_content) else None,
                                        tokens=len(response_content.split()) + len(thinking_content.split())
                                    )
                                    
                                    # Update comparison turn if exists
                                    if comparison_turn and session.is_comparison:
                                        comparison_turn.bridge_response = assistant_message
                                        comparison_turn.save()
                                    
                                    # Update session
                                    session.save()
                                
                                # Send final complete signals
                                if thinking_content and show_thinking:
                                    yield f"data: {json.dumps({
                                        'event': 'complete_thinking',
                                        'content': thinking_content
                                    })}\n\n"
                                
                                yield f"data: {json.dumps({
                                    'event': 'complete_response',
                                    'content': response_content,
                                    'response_id': str(assistant_message.id)
                                })}\n\n"
                                
                                yield f"data: {json.dumps({'event': 'done'})}\n\n"
                                break
                            
                            try:
                                data_chunk = json.loads(line)
                                
                                # Check for choices in the chunk
                                if 'choices' in data_chunk and len(data_chunk['choices']) > 0:
                                    choice = data_chunk['choices'][0]
                                    delta = choice.get('delta', {})
                                    
                                    # Check for reasoning content (thinking process)
                                    if 'reasoning_content' in delta and delta['reasoning_content']:
                                        thinking_content += delta['reasoning_content']
                                        if show_thinking:
                                            yield f"data: {json.dumps({
                                                'event': 'chunk',
                                                'type': 'thinking',
                                                'content': delta['reasoning_content'],
                                                'thinking_so_far': thinking_content
                                            })}\n\n"
                                    
                                    # Check for regular content (final answer)
                                    if 'content' in delta and delta['content']:
                                        response_content += delta['content']
                                        yield f"data: {json.dumps({
                                            'event': 'chunk',
                                            'type': 'content',
                                            'content': delta['content'],
                                            'response_so_far': response_content
                                        })}\n\n"
                                        
                                        # Update status
                                        yield f"data: {json.dumps({
                                            'event': 'status',
                                            'status': 'responding',
                                            'message': 'Generating response...'
                                        })}\n\n"
                            
                            except json.JSONDecodeError:
                                # Skip malformed JSON
                                continue
                            except Exception as e:
                                logger.error(f"Error processing chunk: {str(e)}")
                                continue
                    
                except Exception as e:
                    logger.error(f"Bridge stream generation error: {str(e)}")
                    yield f"data: {json.dumps({'event': 'error', 'error': str(e)})}\n\n"
            
            # Return streaming response
            response = StreamingHttpResponse(
                event_stream(),
                content_type='text/event-stream'
            )
            response['Cache-Control'] = 'no-cache'
            response['X-Accel-Buffering'] = 'no'
            return response
            
        except Exception as e:
            logger.error(f"Bridge chat stream setup error: {str(e)}")
            return JsonResponse({
                'success': False,
                'error': f'Server error: {str(e)}'
            })
    
    return JsonResponse({
        'success': False,
        'error': 'Method not allowed'
    })

@csrf_exempt
def chat_baseline_stream(request):
    """Handle streaming baseline messages for comparison sessions"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            message = data.get('message', '').strip()
            mode = data.get('mode', 'genz')
            session_id = data.get('session_id')
            session_key = data.get('session_key')
            turn_id = data.get('turn_id')
            
            if not message or not session_key:
                return JsonResponse({
                    'success': False,
                    'error': 'Message and session key are required'
                })
            
            # Get session
            session = get_object_or_404(ChatSession, id=session_id, session_key=session_key, is_active=True)
            
            # Use a mutable container to avoid scoping issues
            turn_container = {'turn': None}
            
            # Method 1: Find by turn_id
            if turn_id:
                try:
                    turn_container['turn'] = ComparisonTurn.objects.get(id=turn_id, session=session)
                except ComparisonTurn.DoesNotExist:
                    logger.warning(f"Comparison turn {turn_id} not found")
            
            # Method 2: If no turn_id or not found, find by matching user message
            if not turn_container['turn']:
                # Find user message with similar content created within last 2 minutes
                time_threshold = timezone.now() - timedelta(minutes=2)
                user_messages = ChatMessage.objects.filter(
                    session=session,
                    role='user',
                    created_at__gte=time_threshold
                ).order_by('-created_at')
                
                for user_msg in user_messages:
                    # Check if content is similar (allowing for small differences)
                    if user_msg.content.strip() == message.strip():
                        # Find or create turn for this user message
                        turn_container['turn'] = ComparisonTurn.objects.filter(
                            session=session,
                            user_message=user_msg
                        ).first()
                        
                        if not turn_container['turn']:
                            turn_number = ComparisonTurn.objects.filter(session=session).count() + 1
                            turn_container['turn'] = ComparisonTurn.objects.create(
                                session=session,
                                user_message=user_msg,
                                turn_number=turn_number
                            )
                        break
            
            def event_stream():
                """Generator function for streaming baseline response"""
                try:
                    client = DeepSeekAPIClient()
                    
                    # Generate streaming response
                    response = client.generate_baseline_response(
                        message, 
                        mode, 
                        stream=True
                    )
                    
                    # Variables to accumulate content
                    response_content = ""
                    
                    # Send initial status
                    yield f"data: {json.dumps({
                        'event': 'status', 
                        'status': 'thinking', 
                        'message': 'Starting baseline response...',
                        'session_id': str(session.id)
                    })}\n\n"
                    
                    # Process streaming response
                    for line in response.iter_lines():
                        if line:
                            line = line.decode('utf-8')
                            
                            # Skip empty lines and non-data lines
                            if not line.startswith('data:'):
                                continue
                                
                            # Remove 'data: ' prefix
                            line = line[5:].strip()
                            
                            # Check for end of stream
                            if line == '[DONE]':
                                # Save baseline response to database
                                baseline_response = ChatMessage.objects.create(
                                    session=session,
                                    role='assistant',
                                    content=response_content,
                                    tokens=len(response_content.split())
                                )
                                print("Saved baseline response:", response_content)
                                
                                # Link to comparison turn
                                if turn_container['turn']:
                                    turn_container['turn'].baseline_response = baseline_response
                                    turn_container['turn'].save()
                                    logger.info(f"Linked baseline response to turn {turn_container['turn'].turn_number}")
                                else:
                                    # Create a new turn for this baseline response
                                    # First create a user message for it
                                    user_message = ChatMessage.objects.create(
                                        session=session,
                                        role='user',
                                        content=message,
                                        tokens=len(message.split())
                                    )
                                    print("Saved baseline question:", response_content)
                                    
                                    turn_number = ComparisonTurn.objects.filter(session=session).count() + 1
                                    turn_container['turn'] = ComparisonTurn.objects.create(
                                        session=session,
                                        user_message=user_message,
                                        baseline_response=baseline_response,
                                        turn_number=turn_number
                                    )
                                    logger.warning(f"Created new turn {turn_number} for baseline response")
                                
                                # Update session
                                session.save()
                                
                                # Send final complete signal
                                yield f"data: {json.dumps({
                                    'event': 'complete_response',
                                    'content': response_content,
                                    'response_id': str(baseline_response.id)
                                })}\n\n"
                                
                                yield f"data: {json.dumps({
                                    'event': 'done',
                                    'message': 'Baseline response complete'
                                })}\n\n"
                                break
                            
                            try:
                                data_chunk = json.loads(line)
                                
                                # Check for choices in the chunk
                                if 'choices' in data_chunk and len(data_chunk['choices']) > 0:
                                    choice = data_chunk['choices'][0]
                                    delta = choice.get('delta', {})
                                    
                                    # Check for regular content (final answer)
                                    if 'content' in delta and delta['content']:
                                        response_content += delta['content']
                                        yield f"data: {json.dumps({
                                            'event': 'chunk',
                                            'type': 'content',
                                            'content': delta['content'],
                                            'response_so_far': response_content
                                        })}\n\n"
                                        
                                        # Update status
                                        yield f"data: {json.dumps({
                                            'event': 'status',
                                            'status': 'responding',
                                            'message': 'Generating baseline response...'
                                        })}\n\n"
                            
                            except json.JSONDecodeError:
                                # Skip malformed JSON
                                continue
                            except Exception as e:
                                logger.error(f"Error processing baseline chunk: {str(e)}")
                                continue
                    
                except Exception as e:
                    logger.error(f"Baseline stream generation error: {str(e)}")
                    yield f"data: {json.dumps({'event': 'error', 'error': str(e)})}\n\n"
            
            # Return streaming response
            response = StreamingHttpResponse(
                event_stream(),
                content_type='text/event-stream'
            )
            response['Cache-Control'] = 'no-cache'
            response['X-Accel-Buffering'] = 'no'
            return response
            
        except Exception as e:
            logger.error(f"Baseline chat stream setup error: {str(e)}")
            return JsonResponse({
                'success': False,
                'error': f'Server error: {str(e)}'
            })
    
    return JsonResponse({
        'success': False,
        'error': 'Method not allowed'
    })

@csrf_exempt
def get_comparison_session(request):
    """Get detailed comparison session data"""
    try:
        session_id = request.GET.get('session_id')
        session_key = request.GET.get('session_key')
        
        if not session_id or not session_key:
            return JsonResponse({'success': False, 'error': 'Session ID and key required'})
        
        session = get_object_or_404(ChatSession, id=session_id, session_key=session_key, is_active=True)
        
        if not session.is_comparison:
            return JsonResponse({'success': False, 'error': 'Not a comparison session'})
        
        # Get all turns with their messages
        turns = ComparisonTurn.objects.filter(session=session).order_by('turn_number')
        
        turns_data = []
        for turn in turns:
            # Get user message
            user_message_data = None
            if turn.user_message:
                user_message_data = {
                    'id': str(turn.user_message.id),
                    'content': turn.user_message.content,
                    'created_at': turn.user_message.created_at.isoformat()
                }
            
            # Get bridge response
            bridge_response_data = None
            if turn.bridge_response:
                bridge_response_data = {
                    'id': str(turn.bridge_response.id),
                    'content': turn.bridge_response.content,
                    'thinking': turn.bridge_response.thinking,
                    'created_at': turn.bridge_response.created_at.isoformat()
                }
            
            # Get baseline response - IMPORTANT: Also check if there are any assistant messages that might be baseline
            baseline_response_data = None
            if turn.baseline_response:
                baseline_response_data = {
                    'id': str(turn.baseline_response.id),
                    'content': turn.baseline_response.content,
                    'created_at': turn.baseline_response.created_at.isoformat()
                }
            else:
                # Try to find a baseline response that might not be linked
                # Look for assistant messages after the user message that are not bridge responses
                if turn.user_message:
                    # Get all assistant messages after this user message
                    assistant_messages = ChatMessage.objects.filter(
                        session=session,
                        role='assistant',
                        created_at__gt=turn.user_message.created_at
                    ).order_by('created_at')
                    
                    # If we have a bridge response, look for messages after it
                    if turn.bridge_response:
                        potential_baseline = assistant_messages.filter(
                            created_at__gt=turn.bridge_response.created_at
                        ).first()
                    else:
                        # Otherwise take the first assistant message after the user message
                        potential_baseline = assistant_messages.first()
                    
                    if potential_baseline and potential_baseline != turn.bridge_response:
                        baseline_response_data = {
                            'id': str(potential_baseline.id),
                            'content': potential_baseline.content,
                            'created_at': potential_baseline.created_at.isoformat()
                        }
                        # Update the turn with this baseline response
                        turn.baseline_response = potential_baseline
                        turn.save()
            
            turn_data = {
                'turn_number': turn.turn_number,
                'user_message': user_message_data,
                'bridge_response': bridge_response_data,
                'baseline_response': baseline_response_data,
                'is_complete': turn.is_complete,
                'created_at': turn.created_at.isoformat()
            }
            turns_data.append(turn_data)
        
        return JsonResponse({
            'success': True,
            'session': {
                'id': str(session.id),
                'title': session.title,
                'mode': session.mode,
                'created_at': session.created_at.isoformat(),
                'updated_at': session.updated_at.isoformat(),
                'message_count': session.message_count
            },
            'turns': turns_data
        })
        
    except Exception as e:
        logger.error(f"Get comparison session error: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)})

# Keep existing functions for bridge.html
def research_insights(request):
    """Provide research-based insights from the study"""
    insights = {
        'h1': {
            'title': 'GenZ Initiator-Respondent Differences',
            'findings': [
                '85% higher authenticity markers in initiators',
                '40% more first-person pronouns',
                'Strong negative sentiment correlation in depression subreddits',
                'p < 0.001 statistical significance across all communities'
            ]
        },
        'h2': {
            'title': 'COVID-19 Pandemic Impact',
            'findings': [
                'Sentiment decline: 30% in anxiety communities',
                'Physical symptom discussion increased 38%',
                'Structural reorganization without thematic disruption',
                't=6.483-8.534 (high statistical significance)'
            ]
        },
        'h3': {
            'title': 'Generational Discourse Differences',
            'findings': [
                'GenZ: 60% focus on existential/identity topics',
                'Non-GenZ: 70% focus on practical/clinical management',
                'Systematic linguistic pattern differences',
                'Digital communication style divergence'
            ]
        },
        'key_findings': [
            'Language patterns reliably indicate mental health communication styles',
            'Generational differences are systematic, not random',
            'Digital platforms serve as crucial developmental niches for GenZ',
            'The pandemic acted as psychological intensifier, not disruptor'
        ]
    }
    return JsonResponse(insights)

def home(request):
    """Render the main chat interface"""
    return render(request, 'chat/index.html')

def compare(request):
    """Render the comparison interface"""
    return render(request, 'chat/compare.html')

def single(request):
    """Render the single interface"""
    return render(request, 'chat/single.html')

def bridge(request):
    """Render the bridge interface"""
    return render(request, 'chat/bridge.html')

def baseline(request):
    """Render the baseline interface"""
    return render(request, 'chat/baseline.html')
