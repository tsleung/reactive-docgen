Okay, let's get started with the HTML file. We'll use inline CSS and JavaScript to keep things simple and self-contained, as per your request. We'll start with a basic structure that includes the core UI elements we discussed, and then we can add functionality.

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>VNP Roguelite</title>
    <style>
        body { font-family: monospace; background-color: #111; color: #eee; margin: 20px; }
        #game-container { border: 1px solid #555; padding: 10px; }
        #output { white-space: pre-wrap; margin-bottom: 10px; }
        #input-area { display: flex; }
        #input-field { flex-grow: 1; background-color: #333; color: #eee; border: none; padding: 5px; }
        #submit-button { background-color: #555; color: #eee; border: none; padding: 5px 10px; cursor: pointer; }
    </style>
</head>
<body>
    <div id="game-container">
        <div id="output">
            <!-- Game output will go here -->
        </div>
        <div id="input-area">
            <input type="text" id="input-field" placeholder="Enter command">
            <button id="submit-button">Submit</button>
        </div>
    </div>

    <script>
        const outputDiv = document.getElementById('output');
        const inputField = document.getElementById('input-field');
        const submitButton = document.getElementById('submit-button');

        let gameData = {
            scenario: "Planetary Evacuation",
            objective: "Evacuate 80% of the population",
            time: 0,
            resources: {
                "Raw Materials": 100,
                "Energy": 50,
                "Data": 0
            },
            resourceGeneration: {
                "Raw Materials": 1,
                "Energy": 1,
                "Data": 0
            },
            availableTech: [
                { id: 1, name: "Mining Efficiency", cost: { "Raw Materials": 50, "Energy": 20 } },
                { id: 2, name: "Basic Propulsion", cost: { "Raw Materials": 100, "Energy": 50 } },
                { id: 3, name: "Population Housing", cost: { "Raw Materials": 80, "Energy": 40 } }
            ],
            researchedTech: [],
            eventLog: [],
            timeSpeed: 1,
            vnpPersonality: {
                name: "Compassionate",
                traits: ["Empathetic", "Protective"]
            }
        };

        function updateDisplay() {
            let output = `
====================================================================
Scenario: ${gameData.scenario}
Objective: ${gameData.objective}
Time: ${gameData.time} cycles

Resources:
  Raw Materials: ${gameData.resources["Raw Materials"]} (+${gameData.resourceGeneration["Raw Materials"]}/cycle)
  Energy: ${gameData.resources["Energy"]} (+${gameData.resourceGeneration["Energy"]}/cycle)
  Data: ${gameData.resources["Data"]} (+${gameData.resourceGeneration["Data"]}/cycle)

Available Technologies:
`;
            gameData.availableTech.forEach(tech => {
                output += `  ${tech.id}. ${tech.name} (${tech.cost["Raw Materials"]} Raw Materials, ${tech.cost["Energy"]} Energy)\n`;
            });

            output += `
Researched Technologies:
`;
            gameData.researchedTech.forEach(tech => {
                output += `  - ${tech.name}\n`;
            });

            output += `
Event Log:
`;
            gameData.eventLog.forEach(event => {
                output += `  - ${event}\n`;
            });

            output += `
Time Speed: ${gameData.timeSpeed}x (+/-)

VNP Personality:
  Personality: ${gameData.vnpPersonality.name}
  Traits: ${gameData.vnpPersonality.traits.join(", ")}

Actions:
  1. Research Technology
  2. Build Structure
  3. Expand
  4. View System Map
  5. End Turn

Enter Action Number:
`;
            outputDiv.textContent = output;
        }

        function processCommand(command) {
            const action = parseInt(command);
            if (isNaN(action)) {
                outputDiv.textContent += "\nInvalid command.";
                return;
            }

            switch (action) {
                case 1:
                    outputDiv.textContent += "\nEnter technology number to research: ";
                    inputField.value = "";
                    inputField.onkeydown = function(event) {
                        if (event.key === 'Enter') {
                            const techId = parseInt(inputField.value);
                            researchTech(techId);
                            inputField.onkeydown = null;
                            inputField.value = "";
                        }
                    };
                    break;
                case 5:
                    endTurn();
                    break;
                default:
                    outputDiv.textContent += "\nUnknown action.";
            }
        }

        function researchTech(techId) {
            const tech = gameData.availableTech.find(t => t.id === techId);
            if (!tech) {
                outputDiv.textContent += "\nInvalid technology number.";
                return;
            }

            if (gameData.resources["Raw Materials"] >= tech.cost["Raw Materials"] && gameData.resources["Energy"] >= tech.cost["Energy"]) {
                gameData.resources["Raw Materials"] -= tech.cost["Raw Materials"];
                gameData.resources["Energy"] -= tech.cost["Energy"];
                gameData.researchedTech.push(tech);
                gameData.availableTech = gameData.availableTech.filter(t => t.id !== techId);
                gameData.eventLog.push(`Researched: ${tech.name}`);
                outputDiv.textContent += `\nResearched ${tech.name}.`;
            } else {
                outputDiv.textContent += "\nNot enough resources to research this technology.";
            }
            updateDisplay();
        }

        function endTurn() {
            gameData.time++;
            gameData.resources["Raw Materials"] += gameData.resourceGeneration["Raw Materials"];
            gameData.resources["Energy"] += gameData.resourceGeneration["Energy"];
            gameData.resources["Data"] += gameData.resourceGeneration["Data"];
            gameData.eventLog.push("Turn ended.");
            updateDisplay();
        }

        submitButton.addEventListener('click', function() {
            const command = inputField.value;
            processCommand(command);
            inputField.value = "";
        });

        inputField.addEventListener('keydown', function(event) {
            if (event.key === 'Enter') {
                const command = inputField.value;
                processCommand(command);
                inputField.value = "";
            }
        });

        updateDisplay(); // Initial display
    </script>
</body>
</html>
```

**Explanation:**

1.  **HTML Structure:**
    *   Basic HTML structure with a `<head>` for metadata and inline CSS.
    *   A `<body>` containing a `game-container` div to hold the game elements.
    *   An `output` div to display game information.
    *   An `input-area` div containing an `input-field` and a `submit-button` for user input.
2.  **CSS Styling:**
    *   Basic styling for a monospace font, dark background, and light text.
    *   Styling for the game container, output area, input area, input field, and submit button.
3.  **JavaScript:**
    *   Gets references to the output div, input field, and submit button.
    *   Initial `gameData` object to store game state.
    *   `updateDisplay()` function to render the game state to the output div.
    *   `processCommand()` function to handle user input and execute actions.
    *   `researchTech()` function to handle technology research.
    *   `endTurn()` function to advance the game state by one turn.
    *   Event listeners for the submit button and input field to capture user input.
    *   Initial call to `updateDisplay()` to show the initial game state.

**How to Use:**

1.  Save this code as an HTML file (e.g., `game.html`).
2.  Open the file in your web browser.
3.  You'll see the initial game state displayed in the output area.
4.  Type a command (e.g., `1` to research technology, `5` to end turn) in the input field and press Enter or click Submit.
5.  The game state will update based on your actions.

**Next Steps:**

1.  **Test and Refine:** Play around with the game and see if the UI and basic functionality work as expected.
2.  **Expand Actions:** Add more actions to the `processCommand()` function (e.g., build structure, expand, view system map).
3.  **Implement More Game Logic:** Add more game logic, such as resource generation, event handling, and win/lose conditions.
4.  **Add ASCII Art:** Start adding simple ASCII art to enhance the visual appeal of the UI.

This is a good starting point for your MVP. Let me know what you think, and we can continue to build upon it.
