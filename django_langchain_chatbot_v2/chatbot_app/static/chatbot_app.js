// 会话ID存储（用于多轮对话上下文）
let sessionId = null;

// 异步发送用户消息并接收客服回复
async function sendMessage(){
  // 获取输入框元素
  const input = document.getElementById('input');
  // 获取并去除首尾空格的用户输入文本
  const text = input.value.trim();
  // 如果输入为空，直接返回
  if(!text) return;
  // 获取聊天框元素
  const chatbox = document.getElementById('chatbox');
  // 创建用户消息div，设置类名和文本，并添加到聊天框
  const userDiv = document.createElement('div'); userDiv.className='user'; userDiv.innerText='我: ' + text; chatbox.appendChild(userDiv);
  // 清空输入框并滚动聊天框到底部
  input.value=''; chatbox.scrollTop = chatbox.scrollHeight;

  // 构建请求体，包含消息和会话ID
  const requestBody = {message: text};
  if(sessionId) {
    requestBody.session_id = sessionId;
  }

  // 发送POST请求到后端API，携带用户消息和会话ID
  const resp = await fetch('/api/chat/', {method:'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(requestBody)});
  // 解析返回的JSON数据
  const data = await resp.json();
  
  // 保存会话ID（用于后续对话）
  if(data.session_id) {
    sessionId = data.session_id;
  }
  
  // 创建客服回复div，设置类名和文本（若无回复则显示默认提示），并添加到聊天框
  const botDiv = document.createElement('div'); botDiv.className='bot'; botDiv.innerText='客服: ' + (data.answer || '抱歉，暂时无法回答'); chatbox.appendChild(botDiv);
  // 再次滚动聊天框到底部以显示新消息
  chatbox.scrollTop = chatbox.scrollHeight;
}

// 清空对话历史并开始新会话
function clearChat(){
  sessionId = null;
  const chatbox = document.getElementById('chatbox');
  chatbox.innerHTML = '';
}

// 为发送按钮绑定点击事件，点击时发送消息
document.getElementById('send').addEventListener('click', sendMessage);
// 为输入框绑定键盘事件，按Enter键时发送消息
document.getElementById('input').addEventListener('keydown', function(e){ if(e.key === 'Enter') sendMessage(); });
