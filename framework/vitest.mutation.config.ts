import { defineConfig } from 'vitest/config';
export default defineConfig({ test:{ include:['tests/policy.test.ts'], maxWorkers:1, fileParallelism:false } });
