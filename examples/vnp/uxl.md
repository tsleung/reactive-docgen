Okay, this is an excellent PRD! It's comprehensive and covers all the necessary bases. Let's use this to start building out the UI, focusing on the text-based nature of the game and the core loop.

**UI Design Principles (Text-Based)**

Given the constraints of LLM-driven code generation and the desire for a simple, data-rich interface, we need to adhere to these principles:

1.  **Clarity:** Information should be presented clearly and concisely. Avoid jargon and use simple language.
2.  **Functionality:** The UI should be functional and allow players to easily access the information they need.
3.  **Data-Driven:** The UI should prioritize displaying key data points, such as resources, technologies, and events.
4.  **ASCII Art:** Use simple ASCII art to add visual interest and context.
5.  **Consistency:** Maintain a consistent layout and style throughout the UI.
6.  **Navigation:** Use clear and simple commands for navigating the UI.

**Core UI Elements**

Based on the core loop and the PRD, here are the key UI elements we need to design:

1.  **Scenario Information:**
    *   **Scenario Name:** The name of the current scenario (e.g., "Planetary Evacuation").
    *   **Objective:** A brief description of the player's objective (e.g., "Evacuate 80% of the population").
    *   **Starting Resources:** A list of the player's initial resources (e.g., "Raw Materials: 100, Energy: 50").
    *   **Time Elapsed:** A counter showing the current game time (e.g., "Time: 12 cycles").
2.  **Resource Display:**
    *   **Resource Types:** A list of the different resource types (e.g., "Raw Materials", "Energy", "Data").
    *   **Resource Quantities:** The current amount of each resource (e.g., "Raw Materials: 250, Energy: 120, Data: 50").
    *   **Resource Generation:** The rate at which resources are being generated (e.g., "Raw Materials: +10/cycle, Energy: +5/cycle").
3.  **Technology Display:**
    *   **Available Technologies:** A list of the technologies that the player can research (e.g., "1. Mining Efficiency, 2. Basic Propulsion").
    *   **Technology Cost:** The resource cost of each technology (e.g., "Mining Efficiency: 50 Raw Materials, 20 Energy").
    *   **Researched Technologies:** A list of the technologies that the player has already researched.
4.  **Event Log:**
    *   **Recent Events:** A list of the most recent events that have occurred in the game (e.g., "Meteor shower damaged mining facility", "New research breakthrough achieved").
5.  **Time Dilation Controls:**
    *   **Current Time Speed:** Display the current game speed (e.g., "Time Speed: 1x").
    *   **Time Dilation Options:** Options to increase or decrease the game speed (e.g., "+/-").
6.  **VNP Personality:**
    *   **Current Personality:** Display the current VNP personality (e.g., "Personality: Business-Oriented").
    *   **Personality Traits:** Display the current VNP personality traits (e.g., "Traits: Efficient, Pragmatic").
7.  **Action Menu:**
    *   **Available Actions:** A list of the actions that the player can take (e.g., "1. Research Technology, 2. Build Structure, 3. Expand").
    *   **Action Selection:** Allow the player to select an action using a number or letter.

**Text-Based UI Mockup (Example)**

Here's a basic mockup of how the UI might look in a text-based environment:

```
====================================================================
Scenario: Planetary Evacuation
Objective: Evacuate 80% of the population
Time: 24 cycles

Resources:
  Raw Materials: 320 (+15/cycle)
  Energy: 180 (+8/cycle)
  Data: 75 (+2/cycle)

Available Technologies:
  1. Mining Efficiency (50 Raw Materials, 20 Energy)
  2. Basic Propulsion (100 Raw Materials, 50 Energy)
  3. Population Housing (80 Raw Materials, 40 Energy)

Researched Technologies:
  - Basic Resource Extraction

Event Log:
  - Meteor shower damaged mining facility
  - Population growth increased

Time Speed: 1x (+/-)

VNP Personality:
  Personality: Compassionate
  Traits: Empathetic, Protective

Actions:
  1. Research Technology
  2. Build Structure
  3. Expand
  4. View System Map
  5. End Turn

Enter Action Number:
```

**UI Navigation**

*   **Action Selection:** Players will select actions by entering the corresponding number or letter.
*   **Sub-Menus:** If an action requires further input (e.g., selecting a technology to research), a sub-menu will be displayed.
*   **Back/Cancel:** A command (e.g., "0" or "back") will allow players to return to the previous menu.

**Implementation Notes**

*   **Modular Design:** The UI should be designed in a modular way, so that it can be easily modified and extended.
*   **Clear Functions:** Each UI element should be implemented as a separate function, making it easier to manage and debug.
*   **Data Structures:** Use appropriate data structures (e.g., dictionaries, lists) to store and manage game data.

**Next Steps**

1.  **Refine the Mockup:** Let's refine this mockup and make sure it covers all the necessary information.
2.  **Implement Core UI Functions:** Start implementing the core UI functions, such as displaying resources, technologies, and events.
3.  **Test and Iterate:** Test the UI and gather feedback to identify areas for improvement.
4.  **Add ASCII Art:** Gradually add simple ASCII art to enhance the visual appeal of the UI.

This is a good starting point for the UI. Let me know what you think, and we can refine it further. We can also start implementing some of the core UI functions using the LLM.
