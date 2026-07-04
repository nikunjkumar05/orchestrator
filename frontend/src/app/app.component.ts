import { Component, inject, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';

interface ThoughtLog {
  type: string;
  content: string;
}

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.css']
})
export class AppComponent implements OnDestroy {
  title = 'Prompt-to-Agent Orchestrator';
  prompt: string = '';
  isLoading: boolean = false;
  
  // Real-time states
  streamedAnswer: string = '';
  logs: ThoughtLog[] = [];
  error: string | null = null;
  
  // Approval states
  isWaitingForApproval: boolean = false;
  pendingApproval: { tool: string; args: any; id: string } | null = null;

  private socket: WebSocket | null = null;
  private sanitizer = inject(DomSanitizer);

  executePrompt() {
    if (!this.prompt.trim()) return;

    this.isLoading = true;
    this.streamedAnswer = '';
    this.logs = [];
    this.error = null;
    this.isWaitingForApproval = false;
    this.pendingApproval = null;

    // Determine WebSocket protocol based on page protocol
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${wsProtocol}//${window.location.host}/api/v1/ws`;
    
    // Connect to WebSocket endpoint
    this.socket = new WebSocket(wsUrl);

    this.socket.onopen = () => {
      this.socket?.send(JSON.stringify({ prompt: this.prompt }));
    };

    this.socket.onmessage = (event) => {
      const data = JSON.parse(event.data);

      switch (data.type) {
        case 'token':
          // Append tokens in real-time
          this.streamedAnswer += data.content;
          break;

        case 'status':
          // Log intermediate thought/tool processes
          this.logs.push({ type: 'status', content: data.content });
          break;

        case 'approval_required':
          // Trigger the Approval Banner
          this.isWaitingForApproval = true;
          this.pendingApproval = {
            tool: data.tool,
            args: data.args,
            id: data.id
          };
          this.isLoading = false;
          break;

        case 'done':
          this.isLoading = false;
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

    // Send decision back to server
    this.socket.send(JSON.stringify({
      approved: approved,
      tool_call_id: this.pendingApproval.id
    }));

    // Reset states and continue loading
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
    html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\[(.*?)\]\((.*?)\)/g, '<a href="$2" target="_blank" class="result-link">$1</a>');
    html = html.replace(/\n/g, '<br>');
    return this.sanitizer.bypassSecurityTrustHtml(html);
  }

  formatArgs(args: any): string {
    return JSON.stringify(args, null, 2);
  }

  ngOnDestroy() {
    this.socket?.close();
  }
}