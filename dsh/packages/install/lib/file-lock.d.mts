export function acquireFileLock(path: string, timeout?: number): Promise<() => void>;
