// eslint.config.js
module.exports = {
    env: {
      node: true, // для Node.js
      es2021: true, // поддержка ES2021
    },
    extends: [
      "eslint:recommended", // базовые правила ESLint
      "plugin:@typescript-eslint/recommended", // правила для TypeScript
    ],
    parser: "@typescript-eslint/parser", // парсер для TypeScript
    parserOptions: {
      ecmaVersion: 2021, // версия ECMAScript
      sourceType: "module", // поддержка модулей
    },
    plugins: ["@typescript-eslint"], // плагин для TypeScript
    rules: {
      // Добавьте свои правила или оставьте по умолчанию
    },
  };
