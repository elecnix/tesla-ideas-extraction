export function extractFirstJsonObject(text: string): string | null {
  const codeBlockMatch = text.match(/```json\s*([\s\S]*?)```/i);
  if (codeBlockMatch) {
    return codeBlockMatch[1].trim();
  }

  const firstBrace = text.indexOf("{");
  if (firstBrace === -1) {
    return null;
  }

  let openBraces = 0;
  for (let i = firstBrace; i < text.length; i += 1) {
    const char = text[i];
    if (char === "{") {
      openBraces += 1;
    } else if (char === "}") {
      openBraces -= 1;
      if (openBraces === 0) {
        return text.slice(firstBrace, i + 1);
      }
    }
  }

  return null;
}
