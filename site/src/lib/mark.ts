/* Inline emphasis for copy kept in data files: `*word*` becomes
   <em class="key">word</em>, the pen's colour on the current field.
   Everything else is escaped, so data stays plain text. */
const escape = (s: string): string =>
    s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

export function mark(text: string): string {
    return escape(text).replace(/\*([^*]+)\*/g, '<em class="key">$1</em>');
}
