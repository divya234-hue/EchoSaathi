# EchoSaathi 🎙️

### AI-Powered Communication Assistant

Making communication smarter, simpler, and more accessible through Artificial Intelligence.

---

## 🌟 About EchoSaathi

EchoSaathi is an AI-powered communication assistant designed to make digital communication easier and more accessible.

The project combines speech processing, voice interaction, multilingual communication, and an interactive user interface to create a convenient communication experience.

EchoSaathi focuses on using modern technologies to reduce communication barriers and make voice-based interactions more accessible.

## 🎯 Vision

Our vision is to build technology that makes communication more inclusive.

We aim to develop an intelligent assistant that helps users interact through speech and text while providing a simple, accessible, and user-friendly experience.

## ✨ Key Features

- **Speech-to-Text:** Convert spoken language into text.
- **Text-to-Speech:** Generate spoken output from written text.
- **Multilingual Interface:** Support multiple languages through language selection.
- **Voice Interaction:** Enable voice-assisted communication.
- **Real-Time Communication:** Use WebSocket-based communication between the frontend and backend.
- **Interactive Interface:** Provide an easy-to-use web experience.
- **Retry Support:** Handle retry interactions when communication encounters errors.
- **Customizable Themes:** Provide different interface appearance options.

## 🛠️ Technology Stack

### Frontend
- React
- TypeScript
- Vite
- CSS
- Bun

### Backend
- Python
- WebSocket
- Speech-processing components
- API-based communication

### Development Tools
- Git
- GitHub
- Visual Studio Code

## 📁 Project Structure

```text
EchoSaathi/
│
├── backend/
│   ├── server.py
│   ├── audio.py
│   ├── stt.py
│   ├── chips.py
│   └── tests/
│
├── web/
│   ├── public/
│   ├── src/
│   │   ├── components/
│   │   ├── i18n/
│   │   ├── App.tsx
│   │   ├── main.tsx
│   │   ├── talk.ts
│   │   ├── theme.tsx
│   │   └── ws.ts
│   ├── package.json
│   └── vite.config.ts
│
├── docs/
│
└── README.md
```

## 🚀 Getting Started

Follow these steps to set up the project locally.

### Prerequisites

Make sure you have installed:

- Python
- Bun
- Git
- A code editor such as Visual Studio Code

### 1. Clone the Repository

```bash
git clone https://github.com/divya234-hue/EchoSaathi.git
```

Navigate into the project:

```bash
cd EchoSaathi
```

### 2. Backend Setup

Navigate to the backend directory:

```bash
cd backend
```

Create a Python virtual environment:

```bash
python -m venv .venv
```

Activate the environment on Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Install the project dependencies using the backend dependency configuration:

```bash
uv sync
```

Configure the required environment variables before running services that depend on external integrations.

### 3. Frontend Setup

Open another terminal and navigate to the frontend directory:

```bash
cd web
```

Install dependencies:

```bash
bun install
```

Start the development server:

```bash
bun run dev
```

Open the local URL displayed in your terminal to access the application.

> For the exact backend startup command and required environment variables, follow the backend setup documentation.

## 🌍 Multilingual Experience

EchoSaathi includes a language-selection interface and multilingual text resources.

The current interface includes language resources for:

- English
- Hindi
- Bengali
- Marathi

The goal is to make the application more convenient for users from different language backgrounds.

## 🔐 Privacy and Security

Privacy and security are important considerations when developing communication applications.

- Keep API keys and credentials out of source code.
- Store sensitive configuration in environment variables.
- Never upload private `.env` files to GitHub.
- Validate incoming data before processing it.
- Use secure configurations when deploying the application.

## 🧪 Testing and Development

Testing helps maintain application reliability and makes future improvements easier.

The project includes backend tests and a frontend build workflow.

Backend tests can be executed using the project's configured Python environment and test instructions.

To verify the frontend build:

```bash
cd web
bun install
bun run build
```

## 🚧 Future Improvements

Some possible areas for future development include:

- Improving speech recognition accuracy.
- Expanding multilingual capabilities.
- Enhancing accessibility and usability.
- Improving real-time communication reliability.
- Adding more intelligent conversational features.
- Strengthening security and error handling.
- Improving testing and deployment workflows.

## 🤝 Contributions

Contributions and suggestions are welcome.

If you want to contribute:

1. Create a branch for your changes.
2. Make your improvements.
3. Test your changes.
4. Submit a pull request with a clear description.

## 👩‍💻 Maintainer

**Divya Bharti**

GitHub: [@divya234-hue](https://github.com/divya234-hue)

## 📜 License

See the repository's `LICENSE` file for licensing terms.

---

### Building technology for more accessible communication. ❤️

**EchoSaathi — Every Voice Matters.**
