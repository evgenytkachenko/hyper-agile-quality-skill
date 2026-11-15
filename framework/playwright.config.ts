import { defineConfig } from '@playwright/test';
export default defineConfig({ testDir:'tests', testMatch:'**/*.spec.ts', workers:1, retries:0, timeout:15000,
  use:{ baseURL:'http://127.0.0.1:4173', trace:'retain-on-failure', launchOptions: process.env.PLAYWRIGHT_EXECUTABLE_PATH ? { executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH } : {} }, reporter:[['list'],['json',{ outputFile:'reports/browser.json' }]],
  webServer:{ command:'npm start', url:'http://127.0.0.1:4173', reuseExistingServer:false, timeout:15000 }
});
