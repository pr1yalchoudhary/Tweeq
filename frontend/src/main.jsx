import React from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import './index.css'
import './stage-one.css'
import './stage-two.css'

createRoot(document.getElementById('root')).render(<React.StrictMode><App /></React.StrictMode>)
