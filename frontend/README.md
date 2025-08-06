# IFC Answer Engine Frontend

A modern React-based frontend for the IFC Answer Engine, enabling users to interact with BIM models through natural language queries.

## Features

- **Model Selection**: Browse and select from available BIM projects and models
- **3D BIM Viewer**: Interactive 3D visualization using ThatOpen Components
- **Natural Language Chat**: Ask questions about BIM models in plain English
- **Real-time Loading**: Elegant loading animations and progress indicators
- **Responsive Design**: Clean, modern UI with professional styling

## Technology Stack

- **React 18** with TypeScript
- **Vite** for fast development and building
- **ThatOpen Components** for BIM visualization
- **Tailwind CSS** for styling
- **Axios** for API communication

## Getting Started

### Prerequisites

- Node.js (v18 or later)
- pnpm (recommended) or npm/yarn
- Running IFC Answer Engine API server

### Installation

1. Install dependencies:
```bash
cd frontend
pnpm install
```

2. Start the development server:
```bash
pnpm run dev
```

The application will be available at `http://localhost:3000`.

### Building for Production

```bash
pnpm run build
```

Built files will be in the `dist` directory.

## Architecture

### Components

- **App.tsx**: Main application component managing state and routing
- **ModelSelector**: Interface for browsing and selecting BIM models
- **BIMViewer**: 3D visualization component using ThatOpen Components
- **ChatInterface**: Chat UI for natural language queries
- **LoadingOverlay**: Animated loading states and progress indicators

### API Integration

The frontend communicates with the FastAPI backend through:
- `/models` - Retrieve available BIM models
- `/ask` - Submit natural language questions
- `/models/{id}/ifc` - Download IFC files for visualization

### State Management

State is managed using React hooks:
- Model selection and metadata
- Chat message history
- Loading states and progress
- BIM viewer initialization

## Features

### Model Selection
- Grouped display of projects and models
- Model metadata and descriptions
- Clean, card-based interface

### BIM Viewer
- 3D visualization of IFC models
- Light blue gradient background
- Camera controls and reset functionality
- Model loading progress tracking

### Chat Interface
- Natural language question input
- Message history with timestamps
- Loading animations during processing
- Quick suggestion buttons
- Auto-scrolling message container

### Loading States
- Multi-stage loading indicators
- Animated progress bars
- Contextual loading messages
- Smooth transitions between states

## Styling

The application uses a professional color scheme:
- **Primary**: Blue tones (#0ea5e9 to #0c4a6e)
- **Secondary**: Slate grays (#f8fafc to #0f172a)
- **Background**: Gradient from slate to blue

Custom animations include:
- Shimmer effects for loading text
- Pulse animations for icons
- Smooth transitions between states

## API Configuration

The API base URL is configured in `src/services/api.ts`:
```typescript
const API_BASE_URL = 'http://127.0.0.1:8000';
```

Update this URL if your API server is running on a different address.

## Development

### Available Scripts

- `pnpm run dev` - Start development server
- `pnpm run build` - Build for production
- `pnpm run preview` - Preview production build
- `pnpm run lint` - Run ESLint

### Project Structure

```
frontend/
├── src/
│   ├── components/          # React components
│   ├── services/            # API services
│   ├── types.ts             # TypeScript types
│   ├── App.tsx              # Main application
│   ├── main.tsx             # Entry point
│   └── index.css            # Global styles
├── public/                  # Static assets
├── package.json             # Dependencies
├── vite.config.ts           # Vite configuration
├── tailwind.config.js       # Tailwind configuration
└── tsconfig.json            # TypeScript configuration
```

## Browser Support

- Chrome/Chromium 90+
- Firefox 88+
- Safari 14+
- Edge 90+

## Contributing

1. Follow the existing code style
2. Use TypeScript for type safety
3. Add proper error handling
4. Test across different browsers
5. Ensure responsive design principles

## Troubleshooting

### Common Issues

1. **BIM Viewer not loading**: Check if ThatOpen Components are properly installed
2. **API connection errors**: Verify the API server is running and accessible
3. **Model loading failures**: Ensure IFC files are valid and accessible
4. **Performance issues**: Check browser compatibility and hardware acceleration

### Debug Mode

Enable debug logging by setting localStorage:
```javascript
localStorage.setItem('debug', 'true');
```

## License

This project is part of the IFC Answer Engine suite.