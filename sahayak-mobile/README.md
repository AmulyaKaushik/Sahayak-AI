# Sahayak AI — mobile client

Voice-first banking assistant (Expo / React Native). Full write-up:
[`docs/mobile_client_implementation.md`](../docs/mobile_client_implementation.md).

## Connecting to the backend (Phase F)

1. `cp .env.example .env.local`, then set:
   ```
   EXPO_PUBLIC_USE_MOCK_API=false
   EXPO_PUBLIC_API_BASE_URL=https://sahayak-ai-q5ee.onrender.com
   EXPO_PUBLIC_USE_MOCK_STT=false
   EXPO_PUBLIC_GROQ_API_KEY=<your Groq key>
   ```
2. `npx expo start --clear` (env values are baked in at bundle time, so always restart after editing).
3. Open in Expo Go on the phone. Everything used (incl. `expo-secure-store`) is in Expo Go.

If the backend contract changes, edit only `src/services/api.ts` (paths + types) and, for the demo
mode, `src/services/api-mock.ts`.

### Phone test checklist

The free Render server sleeps after ~15 idle minutes. Open `https://sahayak-ai-q5ee.onrender.com/health`
in a browser a minute before testing or demoing.

- [ ] Fresh install → Login screen. "Create an account" → register with a phone/email + 8+ char password.
- [ ] Onboarding form appears. Try **Skip for now** once (new account) and **Save and continue** once.
- [ ] Ask "Am I eligible for a home loan?" → transcript, reply shown and spoken, ✗/✓ chip, "Needs: …" chips.
- [ ] Say "My monthly income is 30000 and I am 35" → open **My details** (person icon): values appear.
- [ ] Ask a document question ("What is the Sukanya Samriddhi interest rate?") → "Source: …" line.
- [ ] Hindi: "क्या मुझे किसान क्रेडिट कार्ड मिल सकता है?" → Hindi reply, Hindi voice.
- [ ] Kill and reopen the app → still signed in, straight to the chat.
- [ ] Settings → Sign out → back to Login; signing in again shows an empty chat.
- [ ] Wrong password → "Incorrect phone/email or password".
- [ ] Airplane mode mid-question → error card with Retry; turn it off → Retry works.

---

# Welcome to your Expo app 👋

This is an [Expo](https://expo.dev) project created with [`create-expo-app`](https://www.npmjs.com/package/create-expo-app).

## Get started

1. Install dependencies

   ```bash
   npm install
   ```

2. Start the app

   ```bash
   npx expo start
   ```

In the output, you'll find options to open the app in a

- [development build](https://docs.expo.dev/develop/development-builds/introduction/)
- [Android emulator](https://docs.expo.dev/workflow/android-studio-emulator/)
- [iOS simulator](https://docs.expo.dev/workflow/ios-simulator/)
- [Expo Go](https://expo.dev/go), a limited sandbox for trying out app development with Expo

You can start developing by editing the files inside the **app** directory. This project uses [file-based routing](https://docs.expo.dev/router/introduction).

## Get a fresh project

When you're ready, run:

```bash
npm run reset-project
```

This command will move the starter code to the **app-example** directory and create a blank **app** directory where you can start developing.

### Other setup steps

- To set up ESLint for linting, run `npx expo lint`, or follow our guide on ["Using ESLint and Prettier"](https://docs.expo.dev/guides/using-eslint/)
- If you'd like to set up unit testing, follow our guide on ["Unit Testing with Jest"](https://docs.expo.dev/develop/unit-testing/)
- Learn more about the TypeScript setup in this template in our guide on ["Using TypeScript"](https://docs.expo.dev/guides/typescript/)

## Learn more

To learn more about developing your project with Expo, look at the following resources:

- [Expo documentation](https://docs.expo.dev/): Learn fundamentals, or go into advanced topics with our [guides](https://docs.expo.dev/guides).
- [Learn Expo tutorial](https://docs.expo.dev/tutorial/introduction/): Follow a step-by-step tutorial where you'll create a project that runs on Android, iOS, and the web.

## Join the community

Join our community of developers creating universal apps.

- [Expo on GitHub](https://github.com/expo/expo): View our open source platform and contribute.
- [Discord community](https://chat.expo.dev): Chat with Expo users and ask questions.
