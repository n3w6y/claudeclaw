// Patterns that indicate a sensitive value
const SENSITIVE_KEY_PATTERNS = [
  /private.?key/i,
  /api.?key/i,
  /api.?secret/i,
  /passphrase/i,
  /password/i,
  /token/i,
  /secret/i,
  /credential/i,
];

// Regex to find key-value pairs with sensitive keys
const KV_PATTERNS = [
  // JSON: "api_key": "value"
  /("(?:[^"]*(?:key|secret|token|password|private|passphrase|credential)[^"]*)")\s*:\s*"([^"]+)"/gi,
  // ENV: API_KEY=value
  /\b([A-Z_]*(?:KEY|SECRET|TOKEN|PASSWORD|PRIVATE|PASSPHRASE|CREDENTIAL)[A-Z_]*)\s*=\s*["']?([^\s"']+)["']?/gi,
];

export function redact(text: string): string {
  let result = text;

  for (const pattern of KV_PATTERNS) {
    result = result.replace(pattern, (match, key, value) => {
      if (value.length <= 8) {
        return match.replace(value, '****');
      }
      const masked = value.slice(0, 4) + '***' + value.slice(-4);
      return match.replace(value, masked);
    });
  }

  return result;
}

export function isSensitiveFile(filePath: string): boolean {
  const lower = filePath.toLowerCase();
  return (
    lower.includes('.env') ||
    lower.includes('credentials') ||
    lower.includes('secrets') ||
    lower.endsWith('.key') ||
    lower.endsWith('.pem')
  );
}
