import { Component, inject, OnDestroy, OnInit, AfterViewInit, ElementRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';

interface ThoughtLog {
  type: string;
  content: string;
}

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

interface ThreadInfo {
  thread_id: string;
  name: string;
  created_at: string;
  preview: string;
}

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.css']
})
export class AppComponent implements OnDestroy, OnInit, AfterViewInit {
  title = 'Prompt-to-Agent Orchestrator';
  prompt: string = '';
  isLoading: boolean = false;
  isDarkTheme: boolean = true;
  
  streamedAnswer: string = '';
  logs: ThoughtLog[] = [];
  filePreviews: string[] = [];
  messages: ChatMessage[] = [];
  error: string | null = null;
  
  isWaitingForApproval: boolean = false;
  pendingApproval: { tool: string; args: any; id: string } | null = null;

  threadId: string | null = null;
  threads: ThreadInfo[] = [];
  showSidebar: boolean = false;

  private socket: WebSocket | null = null;
  private sanitizer = inject(DomSanitizer);
  private el = inject(ElementRef);

  ngOnInit() {
    const saved = localStorage.getItem('theme');
    if (saved) {
      this.isDarkTheme = saved === 'dark';
    } else {
      this.isDarkTheme = window.matchMedia('(prefers-color-scheme: dark)').matches;
    }
    this.applyTheme();
    this.fetchThreads();
  }

  ngAfterViewInit() {
    const checkSvg = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>';
    const clipboardSvg = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>';
    
    this.el.nativeElement.addEventListener('click', (e: Event) => {
      const target = e.target as HTMLElement;
      const btn = target.closest('.copy-btn') as HTMLButtonElement;
      if (btn) {
        e.stopPropagation();
        const code = btn.getAttribute('data-code');
        if (code) {
          navigator.clipboard.writeText(code).then(() => {
            btn.innerHTML = checkSvg;
            btn.classList.add('copied');
            setTimeout(() => {
              btn.innerHTML = clipboardSvg;
              btn.classList.remove('copied');
            }, 2000);
          });
        }
      }
    });
  }

  toggleTheme() {
    this.isDarkTheme = !this.isDarkTheme;
    localStorage.setItem('theme', this.isDarkTheme ? 'dark' : 'light');
    this.applyTheme();
  }

  private applyTheme() {
    document.documentElement.setAttribute('data-theme', this.isDarkTheme ? 'dark' : 'light');
  }

  handleKeydown(event: KeyboardEvent) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      this.executePrompt();
    }
  }

  autoResize(textarea: HTMLTextAreaElement) {
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 200) + 'px';
  }

  async fetchThreads() {
    try {
      const res = await fetch('/api/v1/threads');
      if (res.ok) {
        this.threads = await res.json();
      }
    } catch (e) {
      console.error('Failed to fetch threads:', e);
    }
  }

  loadThread(threadId: string) {
    this.threadId = threadId;
    this.streamedAnswer = '';
    this.logs = [];
    this.filePreviews = [];
    this.messages = [];
    this.error = null;
    this.isWaitingForApproval = false;
    this.pendingApproval = null;
    this.showSidebar = false;

    this.fetchThreadHistory(threadId);
  }

  private async fetchThreadHistory(threadId: string) {
    try {
      const res = await fetch(`/api/v1/threads/${threadId}/history`);
      if (res.ok) {
        const data = await res.json();
        this.messages = (data.messages || [])
          .filter((m: any) => m.role === 'user' || m.role === 'assistant')
          .map((m: any) => ({ role: m.role, content: m.content }));
      }
    } catch (e) {
      console.error('Failed to load thread history:', e);
    }
  }

  newThread() {
    this.threadId = null;
    this.streamedAnswer = '';
    this.logs = [];
    this.filePreviews = [];
    this.messages = [];
    this.error = null;
    this.isWaitingForApproval = false;
    this.pendingApproval = null;
    this.showSidebar = false;
  }

  executePrompt() {
    if (!this.prompt.trim()) return;

    const userPrompt = this.prompt;
    this.prompt = '';
    this.messages.push({ role: 'user', content: userPrompt });
    this.isLoading = true;
    this.streamedAnswer = '';
    this.logs = [];
    this.filePreviews = [];
    this.error = null;
    this.isWaitingForApproval = false;
    this.pendingApproval = null;

    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${wsProtocol}//${window.location.host}/api/v1/ws`;
    
    this.socket = new WebSocket(wsUrl);

    this.socket.onopen = () => {
      const payload: any = { prompt: userPrompt };
      if (this.threadId) {
        payload.thread_id = this.threadId;
      }
      this.socket?.send(JSON.stringify(payload));
    };

    this.socket.onmessage = (event) => {
      const data = JSON.parse(event.data);

      switch (data.type) {
        case 'thread_id':
          this.threadId = data.thread_id;
          this.fetchThreads();
          break;

        case 'token':
          this.streamedAnswer += data.content;
          break;

        case 'status':
          this.logs.push({ type: 'status', content: data.content });
          break;

        case 'file_preview':
          this.filePreviews.push(data.content);
          break;

        case 'approval_required':
          this.isWaitingForApproval = true;
          this.pendingApproval = {
            tool: data.tool,
            args: data.args,
            id: data.id
          };
          this.isLoading = false;
          break;

        case 'error':
          this.error = data.content;
          this.isLoading = false;
          break;

        case 'done':
          if (this.streamedAnswer) {
            this.messages.push({ role: 'assistant', content: this.streamedAnswer });
          }
          this.streamedAnswer = '';
          this.isLoading = false;
          this.fetchThreads();
          this.socket?.close();
          break;
      }
    };

    this.socket.onerror = (err) => {
      this.error = 'Failed to establish WebSocket connection with server.';
      this.isLoading = false;
      console.error(err);
    };

    this.socket.onclose = () => {
      this.isLoading = false;
    };
  }

  submitApproval(approved: boolean) {
    if (!this.socket || !this.pendingApproval) return;

    this.socket.send(JSON.stringify({
      approved: approved,
      tool_call_id: this.pendingApproval.id
    }));

    this.isWaitingForApproval = false;
    this.pendingApproval = null;
    this.isLoading = true;
  }

  parseMarkdown(text: string): SafeHtml {
    if (!text) return '';
    let html = text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
    
    const clipboardSvg = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>';
    const checkSvg = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>';
    
    const codeBlocks: string[] = [];
    html = html.replace(/```(\w+)?\n?([\s\S]*?)```/g, (match, lang, code) => {
      const idx = codeBlocks.length;
      const language = lang || 'text';
      const cleanCode = code.trimEnd();
      const encoded = cleanCode.replace(/"/g, '&quot;').replace(/'/g, '&#39;');
      codeBlocks.push(`<div class="code-block"><div class="code-header"><span class="lang-label">${language}</span><button class="copy-btn" data-code="${encoded}" title="Copy code">${clipboardSvg}</button></div><pre><code>${cleanCode}</code></pre></div>`);
      return `%%CODEBLOCK_${idx}%%`;
    });
    
    html = html.replace(/^##### (.+)$/gm, '<h5>$1</h5>');
    html = html.replace(/^#### (.+)$/gm, '<h4>$1</h4>');
    html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
    html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
    html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');
    html = html.replace(/^---+\s*$/gm, '<hr>');
    
    html = html.replace(/^> (.+)$/gm, '<blockquote>$1</blockquote>');
    
    const lines = html.split('\n');
    const result: string[] = [];
    let inList: string | null = null;
    
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      
      const ulMatch = line.match(/^\s*[-*] (.+)$/);
      const olMatch = line.match(/^\s*\d+\. (.+)$/);
      
      if (ulMatch) {
        if (inList !== 'ul') {
          if (inList) result.push(`</${inList}>`);
          result.push('<ul>');
          inList = 'ul';
        }
        result.push(`<li>${ulMatch[1]}</li>`);
      } else if (olMatch) {
        if (inList !== 'ol') {
          if (inList) result.push(`</${inList}>`);
          result.push('<ol>');
          inList = 'ol';
        }
        result.push(`<li>${olMatch[1]}</li>`);
      } else {
        if (inList) {
          result.push(`</${inList}>`);
          inList = null;
        }
        if (line.trim() === '' || line.startsWith('<h') || line.startsWith('<hr') || line.startsWith('<blockquote') || line.startsWith('%%CODEBLOCK')) {
          result.push(line);
        } else if (!line.startsWith('<')) {
          result.push(`<p>${line}</p>`);
        } else {
          result.push(line);
        }
      }
    }
    if (inList) result.push(`</${inList}>`);
    
    html = result.join('\n');
    
    html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\*(.*?)\*/g, '<em>$1</em>');
    html = html.replace(/`([^`]+)`/g, '<code class="inline-code">$1</code>');
    html = html.replace(/\[(.*?)\]\((.*?)\)/g, '<a href="$2" target="_blank" class="result-link">$1</a>');
    
    html = html.replace(/%%CODEBLOCK_(\d+)%%/g, (match, idx) => codeBlocks[parseInt(idx)]);
    
    return this.sanitizer.bypassSecurityTrustHtml(html);
  }

  formatArgs(args: any): string {
    return JSON.stringify(args, null, 2);
  }

  formatThreadDate(dateStr: string): string {
    if (!dateStr) return '';
    try {
      const d = new Date(dateStr);
      if (isNaN(d.getTime())) return '';
      const now = new Date();
      const isToday = d.toDateString() === now.toDateString();
      if (isToday) {
        return d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
      }
      return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) + ' ' +
             d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
    } catch {
      return '';
    }
  }

  copyThreadId() {
    if (this.threadId) {
      navigator.clipboard.writeText(this.threadId);
    }
  }

  ngOnDestroy() {
    this.socket?.close();
  }
}
