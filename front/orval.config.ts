import { defineConfig } from 'orval';

// Контракт — specs/openapi.yaml в корне репозитория, общий для back/ и front/.
// common.yaml не самостоятельная спека, а набор компонентов, на которые
// openapi.yaml ссылается через внешний $ref — без explicit allow orval его
// отклоняет как непроверенный внешний документ.
const externalRefs = { allow: ['./common.yaml'] };

export default defineConfig({
  client: {
    input: {
      target: '../specs/openapi.yaml',
      parserOptions: { externalRefs },
    },
    output: {
      client: 'fetch',
      target: 'src/api/generated',
      schemas: 'src/api/generated/schemas',
      mode: 'split',
    },
  },
  zod: {
    input: {
      target: '../specs/openapi.yaml',
      parserOptions: { externalRefs },
    },
    output: {
      client: 'zod',
      target: 'src/api/generated/zod',
      mode: 'split',
      override: {
        zod: {
          version: 4,
          strict: { param: true, query: true, header: true, body: true, response: true },
          dateTimeOptions: { local: true },
        },
      },
    },
  },
});
