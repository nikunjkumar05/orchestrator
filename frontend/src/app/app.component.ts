import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';
import { AgentService, AgentResponse, AgentMessage } from './agent.service';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.css']
})
export class AppComponent {
  title = 'Prompt-to-Agent Orchestrator';
  prompt: string = '';
  isLoading: boolean = false;
  response: AgentResponse | null = null;
  error: string | null = null;

  private agentService = inject(AgentService);
  private sanitizer = inject(DomSanitizer);

  executePrompt() {
    if (!this.prompt.trim()) return;

    this.isLoading = true;
    this.response = null;
    this.error = null;

    this.agentService.executePrompt(this.prompt).subscribe({
      next: (res) => {
        this.response = res;
        this.isLoading = false;
      },
      error: (err) => {
        this.error = 'An error occurred while executing the prompt. Ensure the backend is running.';
        console.error(err);
        this.isLoading = false;
      }
    });
  }

  parseMarkdown(text: string): SafeHtml {
    if (!text) return '';
    
    // Escape HTML first to prevent XSS
    let html = text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
    
    // Bold: **text**
    html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    
    // Links: [label](url)
    html = html.replace(/\[(.*?)\]\((.*?)\)/g, '<a href="$2" target="_blank" class="result-link">$1</a>');
    
    // Line breaks
    html = html.replace(/\n/g, '<br>');
    
    return this.sanitizer.bypassSecurityTrustHtml(html);
  }

  formatMessage(msg: AgentMessage): SafeHtml {
    if (msg.type === 'tool') {
      try {
        const content = msg.content.trim();
        // Convert python dict list string to JSON string safely
        if (content.startsWith('[{') || content.startsWith('{')) {
          const jsonStr = content
            .replace(/'/g, '"')
            .replace(/None/g, 'null')
            .replace(/True/g, 'true')
            .replace(/False/g, 'false');
          const data = JSON.parse(jsonStr);
          
          if (Array.isArray(data)) {
            let html = '<div class="tool-items">';
            data.forEach((item: any) => {
              html += `<div class="tool-item">`;
              if (item.title && item.href) {
                html += `<a href="${item.href}" target="_blank" class="tool-link">${item.title}</a>`;
              }
              if (item.body) {
                html += `<p class="tool-desc">${item.body}</p>`;
              }
              if (!item.title && !item.body) {
                html += `<pre><code>${JSON.stringify(item, null, 2)}</code></pre>`;
              }
              html += `</div>`;
            });
            html += '</div>';
            return this.sanitizer.bypassSecurityTrustHtml(html);
          }
        }
      } catch (e) {
        // Fallback to raw text if parsing fails
      }
    }
    
    return this.parseMarkdown(msg.content);
  }
}
