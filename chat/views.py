import os
import json
import requests
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.views.decorators.http import require_POST
from django.db.models import Q

from .models import ChatSession, ChatMessage
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

class DeepSeekAPIClient:
    def __init__(self):
        self.api_key = settings.DEEPSEEK_API_KEY
        self.base_url = "https://api.deepseek.com/chat/completions"
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
    
    def generate_response(self, message, mode='genz', stream=False, thinking_enabled=True):
        """Generate response using DeepSeek API"""
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
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}")
            raise

@csrf_exempt
@require_POST
def create_session(request):
    """Create a new chat session"""
    try:
        data = json.loads(request.body)
        mode = data.get('mode', 'genz')
        session_key = data.get('session_key')
        is_comparison = data.get('is_comparison', False)
        
        if not session_key:
            return JsonResponse({'success': False, 'error': 'Session key required'})
        
        # Create new session
        session = ChatSession.objects.create(
            mode=mode,
            session_key=session_key,
            title=f"Conversation {ChatSession.objects.filter(session_key=session_key, mode=mode).count() + 1}",
            is_comparison=is_comparison
        )
        
        return JsonResponse({
            'success': True,
            'session': {
                'id': str(session.id),
                'title': session.title,
                'mode': session.mode,
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
        
        if not session_key:
            return JsonResponse({'success': False, 'error': 'Session key required'})
        
        # Get sessions for this user and mode, ordered by most recent
        sessions = ChatSession.objects.filter(
            session_key=session_key,
            mode=mode,
            is_active=True
        ).order_by('-updated_at')
        
        sessions_data = []
        for session in sessions:
            sessions_data.append({
                'id': str(session.id),
                'title': session.title,
                'mode': session.mode,
                'created_at': session.created_at.isoformat(),
                'updated_at': session.updated_at.isoformat(),
                'message_count': session.message_count,
                'last_preview': session.get_first_question_preview()
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
        
        # For comparison sessions, only get user messages and bridge responses
        if session.is_comparison:
            messages = ChatMessage.objects.filter(
                session=session
            ).filter(
                Q(role='user') | Q(message_type='bridge')
            ).order_by('created_at')
        else:
            messages = ChatMessage.objects.filter(session=session).order_by('created_at')
        
        messages_data = []
        for msg in messages:
            # Handle missing message_type (for old messages)
            message_type = getattr(msg, 'message_type', 'normal')
            user_message_id = str(msg.user_message_id) if hasattr(msg, 'user_message') and msg.user_message else None
            
            messages_data.append({
                'id': str(msg.id),
                'role': msg.role,
                'content': msg.content,
                'thinking': msg.thinking,
                'message_type': message_type,
                'created_at': msg.created_at.isoformat(),
                'user_message_id': user_message_id
            })
        
        return JsonResponse({
            'success': True,
            'session': {
                'id': str(session.id),
                'title': session.title,
                'mode': session.mode,
                'is_comparison': session.is_comparison
            },
            'messages': messages_data
        })
        
    except Exception as e:
        logger.error(f"Get messages error: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)})

@csrf_exempt
def get_comparison_messages(request):
    """Get comparison messages for a session"""
    try:
        session_id = request.GET.get('session_id')
        session_key = request.GET.get('session_key')
        
        if not session_id or not session_key:
            return JsonResponse({'success': False, 'error': 'Session ID and key required'})
        
        session = get_object_or_404(ChatSession, id=session_id, session_key=session_key, is_active=True)
        
        if not session.is_comparison:
            return JsonResponse({'success': False, 'error': 'Not a comparison session'})
        
        # Get all messages for comparison session
        messages = ChatMessage.objects.filter(session=session).order_by('created_at')
        
        messages_data = []
        for msg in messages:
            messages_data.append({
                'id': str(msg.id),
                'role': msg.role,
                'content': msg.content,
                'thinking': msg.thinking,
                'message_type': msg.message_type,
                'created_at': msg.created_at.isoformat(),
                'user_message_id': str(msg.user_message_id) if msg.user_message else None
            })
        
        return JsonResponse({
            'success': True,
            'comparison_messages': messages_data
        })
        
    except Exception as e:
        logger.error(f"Get comparison messages error: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)})

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
            user_message_id = data.get('user_message_id')
            
            if not message or not session_key:
                return JsonResponse({
                    'success': False,
                    'error': 'Message and session key are required'
                })
            
            # Get session
            session = get_object_or_404(ChatSession, id=session_id, session_key=session_key, is_active=True)
            
            # Try to get user message, but don't fail if not found
            user_message = None
            if user_message_id:
                try:
                    user_message = ChatMessage.objects.get(id=user_message_id, session=session)
                except ChatMessage.DoesNotExist:
                    logger.warning(f"User message {user_message_id} not found, proceeding without link")
            
            def event_stream():
                """Generator function for streaming baseline response"""
                try:
                    # Prepare messages without system prompt
                    messages = [
                        {"role": "user", "content": message}
                    ]
                    
                    payload = {
                        "model": "deepseek-chat",
                        "messages": messages,
                        "stream": True,
                        "temperature": 0.7,
                        "max_tokens": 1000,
                        "top_p": 0.9,
                        "frequency_penalty": 0.1,
                        "presence_penalty": 0.1
                    }
                    
                    headers = {
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}"
                    }
                    
                    response = requests.post(
                        "https://api.deepseek.com/chat/completions",
                        headers=headers,
                        json=payload,
                        timeout=60,
                        stream=True
                    )
                    response.raise_for_status()
                    
                    # Send initial status
                    yield f"data: {json.dumps({
                        'event': 'status', 
                        'status': 'thinking', 
                        'session_id': str(session.id),
                        'message': 'Starting baseline response...'
                    })}\n\n"
                    
                    # Variables to accumulate content
                    response_content = ""
                    
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
                                # Save baseline assistant message to database
                                ChatMessage.objects.create(
                                    session=session,
                                    role='assistant',
                                    message_type='baseline',
                                    content=response_content,
                                    tokens=len(response_content.split()) if response_content else 0,
                                    thinking=None,
                                    user_message=user_message
                                )
                                
                                # Send final complete signal
                                yield f"data: {json.dumps({
                                    'event': 'complete_response',
                                    'content': response_content
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
                                            'message': 'Generating baseline response...',
                                            'session_id': str(session.id)
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
            is_comparison = data.get('is_comparison', False)
            
            if not message or not session_key:
                return JsonResponse({
                    'success': False,
                    'error': 'Message and session key are required'
                })
            
            # Get session
            session = get_object_or_404(ChatSession, id=session_id, session_key=session_key, is_active=True)
            
            # Update session title from first message if needed
            if session.message_count == 0:
                session.update_title_from_message(message)
            
            # Save user message
            user_message = ChatMessage.objects.create(
                session=session,
                role='user',
                content=message,
                tokens=len(message.split())
            )
            
            def event_stream():
                """Generator function for streaming response"""
                try:
                    client = DeepSeekAPIClient()
                    
                    # Generate streaming response
                    response = client.generate_response(
                        message, 
                        mode, 
                        stream=True,
                        thinking_enabled=show_thinking
                    )
                    
                    # Variables to accumulate content
                    thinking_content = ""
                    response_content = ""
                    
                    # Send initial status with session info
                    yield f"data: {json.dumps({
                        'event': 'status', 
                        'status': 'thinking', 
                        'message': 'Starting analysis...',
                        'session_id': str(session.id),
                        'session_title': session.title
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
                                # Save assistant message to database
                                assistant_message = ChatMessage.objects.create(
                                    session=session,
                                    role='assistant',
                                    message_type='bridge' if session.is_comparison else 'normal',
                                    content=response_content,
                                    thinking=thinking_content if (show_thinking and thinking_content) else None,
                                    tokens=len(response_content.split()) + len(thinking_content.split()) if response_content else 0,
                                    user_message=user_message if session.is_comparison else None
                                )
                                
                                # Update session timestamp
                                session.save()
                                
                                # Send final complete signals
                                if thinking_content and show_thinking:
                                    yield f"data: {json.dumps({
                                        'event': 'complete_thinking',
                                        'content': thinking_content
                                    })}\n\n"
                                
                                yield f"data: {json.dumps({
                                    'event': 'complete_response',
                                    'content': response_content
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
                    logger.error(f"Stream generation error: {str(e)}")
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
            logger.error(f"Chat stream setup error: {str(e)}")
            return JsonResponse({
                'success': False,
                'error': f'Server error: {str(e)}'
            })
    
    return JsonResponse({
        'success': False,
        'error': 'Method not allowed'
    })

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

@csrf_exempt
def last_user_message(request):
    """Get the last user message ID for a session"""
    try:
        session_id = request.GET.get('session_id')
        session_key = request.GET.get('session_key')
        
        if not session_id or not session_key:
            return JsonResponse({'success': False, 'error': 'Session ID and key required'})
        
        session = get_object_or_404(ChatSession, id=session_id, session_key=session_key, is_active=True)
        
        # Get the last user message
        last_user_msg = ChatMessage.objects.filter(
            session=session,
            role='user'
        ).order_by('-created_at').first()
        
        if last_user_msg:
            return JsonResponse({
                'success': True,
                'message_id': str(last_user_msg.id)
            })
        else:
            return JsonResponse({
                'success': False,
                'error': 'No user messages found'
            })
            
    except Exception as e:
        logger.error(f"Last user message error: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)})
