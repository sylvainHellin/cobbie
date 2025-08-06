# Requirements for the Frontend of the Ifc Answer Engine

## Context

This is the GUI for users to ask questions related to a BIM model using natural language.

## User Personas & Use Cases

### Target Users:

Stakeholders in the property development chain who lack BIM expertise but need to access information contained in BIM models.

### Typical Scenarios:
Property managers querying room dimensions, material specifications, or equipment locations
Facility managers asking about maintenance access points or system configurations
Project stakeholders reviewing design elements without needing BIM software expertise
Non-technical team members extracting project information for reports or decision-making

### Key Value Proposition:

Enable natural language queries against BIM data without requiring specialized BIM software knowledge or training.

## Functionalities

### Model Selection

The models available to query are stored directly on the FastAPI server.
In order to use the chat function, the user should first need to select a project, and then a specific model from this project.

### BIM Viewer

A BIM viewer should render the model selected by the user (use the API endpoint to get the .ifc file, and render it using the specified components).
For the implementation, try to combine:
 The IFC loader: https://docs.thatopen.com/Tutorials/Components/Core/IfcLoader
 The IFC item finder: https://docs.thatopen.com/Tutorials/Components/Core/ItemsFinder
 For the visual style, use the one of the item finder (no grid). If possible, with a light blue background instead of black.
The BIM viewer should be displayed only after the user has selected a project and model.

### Chat Interface

The chat interface should be located on the right of the window. We are targeting desktop users, so creating a responsive design is not mandatory.
This interface should be displayed only after the user has selected a project and model.

## API Integration Points

The frontend will integrate with the FastAPI server through the following endpoints:
Model listing: Retrieve available projects and models for selection
IFC file retrieval: Download the .ifc file for the selected model to render in the BIM viewer
Natural language queries: Send user questions about the selected model and receive AI-generated responses

## Chat-to-BIM Viewer Integration

To enhance the user experience for non-BIM experts:
When the AI responds to queries about specific building elements, the BIM viewer should ideally highlight or focus on the relevant components (if technically feasible with the chosen IFC components)
This visual correlation helps users understand spatial relationships and locations without requiring BIM navigation expertise
Consider implementing basic viewer controls (zoom to element, reset view) that can be triggered programmatically based on chat responses

## User Experience

The interface should be clean and minimalistic
It should have a tasty and classy color scheme
It can take several seconds (10-30) before receiving the answer from the endpoint. For this, we need to have some nice animations, and not just a single spinner. For this, the animations from cursor (IDE) are quite nice: showing messages like 'loading BIM model'; 'fetching information'; 'processing results'; ..., with some nice moving highlight on the text, make the time pass faster. Important is that no spinner/loader/etc. stays active for more than a couple of seconds, so that the user doesn't have the feeling the app is stuck.
