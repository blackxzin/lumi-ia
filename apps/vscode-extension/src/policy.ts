import * as path from 'node:path';

export function safeRelative(root: string, filename: string): string | undefined {
  const relative = path.relative(root, filename);
  const parts = relative.split(path.sep);
  if (!relative || path.isAbsolute(relative) || parts.some(part => {
    const p = part.toLowerCase();
    return p === '..' || p.startsWith('.') || ['node_modules', 'credentials', 'secrets', 'id_rsa', 'id_ed25519'].includes(p)
      || /\.(pem|key|p12|pfx|db|sqlite)$/.test(p) || p.includes('credential') || p.includes('secret');
  })) return undefined;
  return parts.join('/');
}
