// Poker Engine Web UI
class PokerUI {
    constructor() {
        this.ws = null;
        this.token = localStorage.getItem('auth_token');
        this.playerId = localStorage.getItem('player_id') || null;
        this.username = localStorage.getItem('username') || null;
        this.tableId = 'table-1';
        this.currentSeat = null;
        this.expectedVersion = 0;
        this.baseUrl = 'http://localhost:8000';
        this.wsUrl = 'ws://localhost:8000';
        
        // Check if logged in
        if (!this.token || !this.playerId) {
            window.location.href = 'login.html';
            return;
        }
        
        this.initializeElements();
        this.attachEventListeners();
        this.initializeSeats();
        this.updateUserDisplay();
    }

    initializeElements() {
        // Connection
        this.tableIdInput = document.getElementById('tableId');
        this.connectBtn = document.getElementById('connectBtn');
        this.disconnectBtn = document.getElementById('disconnectBtn');
        this.connectionStatus = document.getElementById('connectionStatus');
        this.usernameDisplay = document.getElementById('usernameDisplay');
        
        // Status
        this.currentStreet = document.getElementById('currentStreet');
        this.currentBet = document.getElementById('currentBet');
        this.playerCount = document.getElementById('playerCount');
        this.tableIdDisplay = document.getElementById('tableIdDisplay');
        this.helpMessage = document.getElementById('helpMessage');
        this.playerInfo = document.getElementById('playerInfo');
        this.handInfo = document.getElementById('handInfo');
        this.startHandBtn = document.getElementById('startHandBtn');
        
        // Table
        this.seatsContainer = document.getElementById('seats');
        this.communityCards = document.getElementById('communityCards');
        this.potsContainer = document.getElementById('pots');
        
        // Actions
        this.actionPanel = document.getElementById('actionPanel');
        this.foldBtn = document.getElementById('foldBtn');
        this.checkBtn = document.getElementById('checkBtn');
        this.callBtn = document.getElementById('callBtn');
        this.betBtn = document.getElementById('betBtn');
        this.raiseBtn = document.getElementById('raiseBtn');
        this.betAmountInput = document.getElementById('betAmount');
        this.actionInfo = document.getElementById('actionInfo');
        
        // Controls
        this.stackInput = document.getElementById('stackInput');
        this.addPlayerBtn = document.getElementById('addPlayerBtn');
        this.playerList = document.getElementById('playerList');
        this.seatedPlayers = []; // Track seated players: [{seatId, playerId, stack}]
        this.lastState = null; // Store last state from WebSocket
        
        // History
        this.handHistory = document.getElementById('handHistory');
        this.playerStats = document.getElementById('playerStats');
    }

    initializeSeats() {
        // Create 9 seat elements
        for (let i = 0; i < 9; i++) {
            const seat = document.createElement('div');
            seat.className = 'seat empty';
            seat.id = `seat-${i}`;
            seat.innerHTML = `
                <div class="seat-info">
                    <div class="seat-name">Seat ${i}</div>
                    <div class="seat-stack">-</div>
                    <div class="seat-status">Empty</div>
                </div>
            `;
            this.seatsContainer.appendChild(seat);
        }
    }

    attachEventListeners() {
        this.connectBtn.addEventListener('click', () => this.connect());
        this.disconnectBtn.addEventListener('click', () => this.disconnect());
        
        const joinTableBtn = document.getElementById('joinTableBtn');
        if (joinTableBtn) {
            joinTableBtn.addEventListener('click', () => this.joinTable());
        }
        
        // Also support old button ID for backward compatibility
        const sitDownBtn = document.getElementById('sitDownBtn');
        if (sitDownBtn) {
            sitDownBtn.addEventListener('click', () => this.joinTable());
        }
        this.startHandBtn.addEventListener('click', () => this.startHand());
        
        this.foldBtn.addEventListener('click', () => this.act('FOLD'));
        this.checkBtn.addEventListener('click', () => this.act('CHECK'));
        this.callBtn.addEventListener('click', () => this.act('CALL'));
        this.betBtn.addEventListener('click', () => this.act('BET'));
        this.raiseBtn.addEventListener('click', () => this.act('RAISE'));
    }

    updateUserDisplay() {
        if (this.username) {
            this.usernameDisplay.textContent = this.username;
        }
    }

    logout() {
        localStorage.removeItem('auth_token');
        localStorage.removeItem('player_id');
        localStorage.removeItem('username');
        window.location.href = 'login.html';
    }

    async connect() {
        this.tableId = this.tableIdInput.value || 'table-1';
        
        if (!this.tableId) {
            alert('Please enter Table ID');
            return;
        }
        
        if (!this.token || !this.playerId) {
            alert('Not logged in. Redirecting to login...');
            window.location.href = 'login.html';
            return;
        }
        
        // Update table ID display
        this.tableIdDisplay.textContent = this.tableId;
        
        try {
            // Connect WebSocket with authentication token in query params
            const tokenParam = this.token ? `?token=${encodeURIComponent(this.token)}` : '';
            const wsUrl = `${this.wsUrl}/ws/tables/${this.tableId}${tokenParam}`;
            this.ws = new WebSocket(wsUrl);
            
            this.ws.onopen = () => {
                this.updateConnectionStatus(true);
                this.log('Connected to table:', this.tableId);
            };
            
            this.ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                this.handleMessage(data);
            };
            
            this.ws.onerror = (error) => {
                this.log('WebSocket error:', error);
                alert('Failed to connect. Make sure the server is running.');
            };
            
            this.ws.onclose = () => {
                this.updateConnectionStatus(false);
                this.log('Disconnected from table');
            };
            
            // Load initial state
            await this.loadTableState();
            
        } catch (error) {
            this.log('Connection error:', error);
            alert('Failed to connect: ' + error.message);
        }
    }

    disconnect() {
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
        this.updateConnectionStatus(false);
    }

    updateConnectionStatus(connected) {
        if (connected) {
            this.connectionStatus.textContent = 'Connected';
            this.connectionStatus.className = 'status connected';
            this.connectBtn.disabled = true;
            this.disconnectBtn.disabled = false;
        } else {
            this.connectionStatus.textContent = 'Disconnected';
            this.connectionStatus.className = 'status disconnected';
            this.connectBtn.disabled = false;
            this.disconnectBtn.disabled = true;
        }
    }

    async loadTableState() {
        // Load current state via REST API (fallback if WebSocket fails)
        // Note: This requires authentication, so it may fail if token is invalid
        try {
            const headers = {};
            if (this.token) {
                headers['Authorization'] = `Bearer ${this.token}`;
            }
            
            const response = await fetch(`${this.baseUrl}/api/v1/tables/${this.tableId}/snapshot`, {
                headers
            });
            
            if (!response.ok) {
                if (response.status === 401) {
                    // Token expired, redirect to login
                    this.logout();
                    return;
                }
                // 422 or other errors - just log, don't throw
                console.warn('Failed to load table state via REST:', response.status);
                return;
            }
            const data = await response.json();
            this.updateTableState(data);
        } catch (error) {
            // Silently fail - WebSocket will provide state updates
            console.warn('Failed to load table state:', error);
        }
    }

    handleMessage(data) {
        console.log('WebSocket message received:', data.type, data);
        
        if (data.type === 'state') {
            // Full state update - use it directly
            const playerCount = data.data.seats ? data.data.seats.filter(s => s !== null).length : 0;
            console.log(`[UI] Updating state from WebSocket. Players: ${playerCount}, Version: ${data.version || 'N/A'}`);
            console.log('[UI] Seats data:', data.data.seats);
            // Debug: Check for hole cards
            data.data.seats?.forEach((seat, idx) => {
                if (seat && seat.hole_cards) {
                    console.log(`[UI] Seat ${idx} has hole_cards:`, seat.hole_cards, 'player_id:', seat.player_id, 'my playerId:', this.playerId);
                }
            });
            this.lastState = data.data; // Store state for later use
            this.updateTableState(data.data);
            // Update expected version from state
            if (data.version !== undefined) {
                this.expectedVersion = data.version;
            }
        } else if (data.type === 'event') {
            // Event received - add to history
            this.handleEvent(data);
            // State will be updated via broadcast - don't call REST API
            // The server will broadcast a state message after events
        } else if (data.type === 'command_accepted') {
            this.expectedVersion = data.new_version;
            this.log('Command accepted, version:', data.new_version);
        } else if (data.type === 'error') {
            this.handleError({ message: data.message });
        }
    }

    handleEvent(event) {
        this.addToHistory(event);
        
        // State will be updated via WebSocket broadcast (state message)
        // No need to reload here - the broadcast will send full state
    }

    updateTableState(state) {
        // Ensure seats array exists and has 9 elements
        if (!state.seats || state.seats.length < 9) {
            const seats = state.seats || [];
            state.seats = [...seats, ...Array(9 - seats.length).fill(null)];
        }
        
        // Count seated players (any seat that's not null)
        const seatedCount = state.seats.filter(s => s !== null).length;
        console.log(`[UI] updateTableState: ${seatedCount} players seated`);
        
        // Update street and bet
        this.currentStreet.textContent = state.street || 'WAITING';
        this.currentBet.textContent = `Bet: ${state.current_bet || 0}`;
        
        // Count active players (in a hand) - for game logic
        const activePlayers = state.seats.filter(s => s && (s.status === 'ACTIVE' || s.status === 'ALL_IN')).length;
        this.playerCount.textContent = `Players: ${seatedCount}`;
        
        // Sync seated players list with state
        this.seatedPlayers = [];
        state.seats.forEach((seat, index) => {
            if (seat) {
                this.seatedPlayers.push({
                    seatId: index,
                    playerId: seat.player_id || `player${index + 1}`, // Display-friendly ID
                    stack: seat.stack
                });
            }
        });
        console.log(`[UI] Seated players list:`, this.seatedPlayers.map(p => `${p.playerId} (Seat ${p.seatId + 1})`));
        this.updatePlayerList();
        
        // Update seats
        state.seats.forEach((seat, index) => {
            this.updateSeat(index, seat);
        });
        
        // Update community cards
        this.updateCommunityCards(state.community_cards || []);
        
        // Update pots
        this.updatePots(state.pots || []);
        
        // Show/hide action panel
        this.updateActionPanel(state);
        
        // Update UI guidance - use seatedCount (not activePlayers) for determining if we can start a hand
        this.updateGuidance(seatedCount, state);
        
        console.log('State updated. Seated players:', this.seatedPlayers.length);
    }

    updateSeat(index, seat) {
        const seatEl = document.getElementById(`seat-${index}`);
        const seatNumber = index + 1; // Display as 1-9 instead of 0-8
        
        if (!seat) {
            seatEl.className = 'seat empty';
            seatEl.innerHTML = `
                <div class="seat-info">
                    <div class="seat-name">Seat ${seatNumber}</div>
                    <div class="seat-stack">-</div>
                </div>
            `;
            return;
        }
        
        const isActive = seat.status === 'ACTIVE' || seat.status === 'ALL_IN';
        const isToAct = seat.status === 'ACTIVE' && seat.seat_id === this.currentSeat;
        
        seatEl.className = `seat ${isActive ? 'active' : ''} ${isToAct ? 'to-act' : ''}`;
        
        // Minimal display - just essential info
        const playerName = seat.player_id || `Seat ${seatNumber}`;
        const shortName = playerName.length > 8 ? playerName.substring(0, 8) + '...' : playerName;
        
        // Show hole cards if this is the current player
        let holeCardsHtml = '';
        if (seat.hole_cards && seat.hole_cards.length === 2) {
            // SIMPLE: Show cards if player_id matches
            const isMySeat = seat.player_id === this.playerId;
            if (isMySeat) {
                holeCardsHtml = `
                    <div class="hole-cards" style="display: flex; gap: 4px; margin-top: 4px;">
                        ${seat.hole_cards.map(card => {
                            const cardEl = this.createCardElement(card);
                            return cardEl.outerHTML;
                        }).join('')}
                    </div>
                `;
                console.log(`[UI] ✓ Displaying hole cards for seat ${index} (player_id=${seat.player_id})`);
            } else {
                console.log(`[UI] Not showing cards for seat ${index}: player_id=${seat.player_id}, my playerId=${this.playerId}`);
            }
        }
        
        seatEl.innerHTML = `
            <div class="seat-info">
                <div class="seat-name">${shortName}</div>
                <div class="seat-stack">${seat.stack}</div>
                ${seat.committed_total > 0 ? `<div class="seat-status" style="background: var(--bg-tertiary); color: var(--text-secondary); margin-top: 4px; font-size: 9px;">${seat.committed_total}</div>` : `<div class="seat-status ${seat.status}">${seat.status}</div>`}
                ${holeCardsHtml}
            </div>
        `;
    }

    updateCommunityCards(cards) {
        this.communityCards.innerHTML = '';
        
        if (cards.length === 0) {
            // Show placeholders
            ['Flop', 'Turn', 'River'].forEach(label => {
                const placeholder = document.createElement('div');
                placeholder.className = 'card-placeholder';
                placeholder.textContent = label;
                this.communityCards.appendChild(placeholder);
            });
            return;
        }
        
        cards.forEach(card => {
            const cardEl = this.createCardElement(card);
            this.communityCards.appendChild(cardEl);
        });
    }

    createCardElement(card) {
        const cardEl = document.createElement('div');
        cardEl.className = 'card';
        
        // Handle both {rank: 2, suit: 0} and {rank: {value: 2}, suit: {value: 0}} formats
        const rankValue = typeof card.rank === 'object' ? card.rank.value : card.rank;
        const suitValue = typeof card.suit === 'object' ? card.suit.value : card.suit;
        
        const rank = this.getRankSymbol(rankValue);
        const suit = this.getSuitSymbol(suitValue);
        const isRed = suitValue === 1 || suitValue === 2; // Diamonds or Hearts
        
        cardEl.className += isRed ? ' red' : ' black';
        cardEl.innerHTML = `
            <div class="card-rank">${rank}</div>
            <div class="card-suit">${suit}</div>
        `;
        
        return cardEl;
    }

    getRankSymbol(rank) {
        const ranks = { 2: '2', 3: '3', 4: '4', 5: '5', 6: '6', 7: '7', 8: '8', 9: '9', 10: '10', 11: 'J', 12: 'Q', 13: 'K', 14: 'A' };
        return ranks[rank] || rank;
    }

    getSuitSymbol(suit) {
        const suits = { 0: '♣', 1: '♦', 2: '♥', 3: '♠' };
        return suits[suit] || suit;
    }

    updatePots(pots) {
        this.potsContainer.innerHTML = '';
        pots.forEach((pot, index) => {
            const potEl = document.createElement('div');
            potEl.className = 'pot';
            potEl.textContent = `${index === 0 ? 'Main' : `Side ${index}`} Pot: $${pot.amount}`;
            this.potsContainer.appendChild(potEl);
        });
        
        if (pots.length === 0) {
            const potEl = document.createElement('div');
            potEl.className = 'pot';
            potEl.textContent = 'Main Pot: $0';
            this.potsContainer.appendChild(potEl);
        }
    }

    updateActionPanel(state) {
        // Find if current player can act
        const playerSeat = state.seats.findIndex(s => s && s.player_id === this.playerId);
        
        if (playerSeat >= 0) {
            const seat = state.seats[playerSeat];
            if (seat.status === 'ACTIVE') {
                this.currentSeat = playerSeat;
                this.actionPanel.style.display = 'block';
                this.updateActionButtons(state, seat);
                return;
            }
        }
        
        this.actionPanel.style.display = 'none';
        this.currentSeat = null;
    }

    updateActionButtons(state, seat) {
        // Enable/disable buttons based on legal actions
        const callAmount = state.current_bet - (seat.committed_street || 0);
        
        // Minimal info display
        this.actionInfo.innerHTML = `
            <div>Stack ${seat.stack} · Bet ${state.current_bet} · Call ${callAmount}</div>
        `;
        
        // Enable buttons based on situation
        this.foldBtn.disabled = state.current_bet === 0;
        this.checkBtn.disabled = state.current_bet > 0;
        this.callBtn.disabled = state.current_bet === 0 || callAmount === 0;
        this.betBtn.disabled = state.current_bet > 0;
        this.raiseBtn.disabled = state.current_bet === 0;
    }

    findNextAvailableSeat(state) {
        // Find first empty seat (auto-assign)
        for (let i = 0; i < 9; i++) {
            if (!state.seats[i]) {
                return i;
            }
        }
        return null; // Table full
    }
    
    // Alias for backward compatibility
    async sitDown() {
        return this.joinTable();
    }

    async addPlayer() {
        // In real multiplayer, each player sits themselves down
        // This function is for demo/testing mode only
        const stack = parseInt(this.stackInput.value);
        
        if (isNaN(stack) || stack < 100) {
            alert('Please enter a valid stack (minimum 100 chips)');
            return;
        }
        
        if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
            alert('Please connect to a table first');
            return;
        }
        
        // Get current state to find available seat
        const state = await this.getCurrentState();
        const seatId = this.findNextAvailableSeat(state);
        
        if (seatId === null) {
            alert('Table is full (9 players maximum)');
            return;
        }
        
        // Generate unique player ID based on current seated players count
        const currentPlayerCount = state.seats.filter(s => s !== null).length;
        const playerId = `player${currentPlayerCount + 1}`;
        
        const command = {
            type: 'sit_down',
            data: {
                seat_id: seatId,
                stack: stack,
                player_id: playerId
            },
            idempotency_key: `sit-${Date.now()}-${playerId}-${seatId}`,
            expected_version: this.expectedVersion
        };
        
        this.sendCommand(command);
        
        // Wait a bit for the command to process, then refresh state
        setTimeout(() => {
            this.loadTableState();
        }, 200);
    }
    
    async joinTable() {
        // Auto-assign seat and join table with selected chip amount
        const stack = parseInt(this.stackInput.value) || 1000;
        
        if (stack < 100) {
            alert('Minimum stack is 100 chips');
            return;
        }
        
        if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
            alert('Please connect to a table first');
            return;
        }
        
        // Get current state to find available seat
        const state = await this.getCurrentState();
        
        // Check if player is already seated
        const alreadySeated = state.seats.some(s => s && s.player_id === this.playerId);
        if (alreadySeated) {
            alert('You are already seated at this table');
            return;
        }
        
        // Auto-assign first available seat
        const seatId = this.findNextAvailableSeat(state);
        
        if (seatId === null) {
            alert('Table is full (9 players maximum)');
            return;
        }
        
        // Join table with auto-assigned seat
        const command = {
            type: 'sit_down',
            data: {
                seat_id: seatId,
                stack: stack,
                player_id: this.playerId
            },
            idempotency_key: `join-${this.playerId}-${Date.now()}`,
            expected_version: this.expectedVersion
        };
        
        this.sendCommand(command);
        
        // Disable join button while processing
        const joinBtn = document.getElementById('joinTableBtn');
        if (joinBtn) {
            joinBtn.disabled = true;
            joinBtn.textContent = 'Joining...';
        }
        
        // State will update via WebSocket broadcast
    }
    
    async quickAddPlayers(count) {
        if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
            alert('Please connect to a table first');
            return;
        }
        
        const stack = parseInt(this.stackInput.value) || 1000;
        
        // Add players one by one with a small delay
        for (let i = 0; i < count; i++) {
            await this.addPlayer();
            // Wait a bit between adds to ensure commands process
            await new Promise(resolve => setTimeout(resolve, 300));
        }
    }
    
    removePlayer(seatId) {
        if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
            alert('Please connect to a table first');
            return;
        }
        
        // Find player to remove
        const player = this.seatedPlayers.find(p => p.seatId === seatId);
        if (!player) return;
        
        // Send stand up command (would need to be implemented)
        // For now, just remove from local list and refresh
        this.seatedPlayers = this.seatedPlayers.filter(p => p.seatId !== seatId);
        this.updatePlayerList();
        
        // Reload state to sync with server
        setTimeout(() => this.loadTableState(), 100);
    }
    
    updatePlayerList() {
        if (this.seatedPlayers.length === 0) {
            this.playerList.innerHTML = '<p class="empty">No players at table</p>';
        } else {
            this.playerList.innerHTML = this.seatedPlayers.map(player => {
                const seatNumber = player.seatId + 1; // Display as 1-9
                return `
                <div class="player-item">
                    <div class="player-item-info">
                        <div class="player-item-name">${player.playerId}</div>
                        <div class="player-item-details">Seat ${seatNumber} · ${player.stack} chips</div>
                    </div>
                </div>
            `;
            }).join('');
        }
        
        // Update join button state
        const joinBtn = document.getElementById('joinTableBtn') || document.getElementById('sitDownBtn');
        if (joinBtn) {
            const isSeated = this.seatedPlayers.some(p => p.playerId === this.playerId);
            joinBtn.disabled = isSeated || !this.ws || this.ws.readyState !== WebSocket.OPEN;
            joinBtn.textContent = isSeated ? 'Already Joined' : 'Join Table';
        }
        
        // Update guidance - use seated players count
        const currentState = this.lastState || { street: 'WAITING', seats: [] };
        const seatedCount = this.seatedPlayers.length;
        this.updateGuidance(seatedCount, currentState);
    }

    async standUp() {
        if (this.currentSeat === null) {
            alert('You are not seated');
            return;
        }
        
        // Stand up would be a new command type
        this.log('Stand up not yet implemented');
    }

    updateGuidance(seatedPlayers, state) {
        // Update step indicators
        // seatedPlayers = count of seated players (not active-in-hand status)
        const step1 = document.getElementById('step1');
        const step2 = document.getElementById('step2');
        const step3 = document.getElementById('step3');
        
        // Step 1: Connected
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            step1.classList.add('active');
        } else {
            step1.classList.remove('active');
        }
        
        // Step 2: Players seated (use seatedPlayers count, not active-in-hand status)
        const street = state?.street || 'WAITING';
        if (seatedPlayers >= 2) {
            step2.classList.add('active');
            this.playerInfo.innerHTML = `<strong>${seatedPlayers} players ready ✓</strong> - You can start a hand now`;
            this.playerInfo.className = 'info-text success';
            // Only enable start hand if we're in WAITING state (no hand active)
            this.startHandBtn.disabled = (street !== 'WAITING');
            this.handInfo.textContent = street === 'WAITING' ? 'Ready to start' : `Hand in progress (${street})`;
            this.handInfo.className = 'info-text success';
        } else {
            step2.classList.remove('active');
            const needed = 2 - seatedPlayers;
            if (seatedPlayers === 0) {
                this.playerInfo.innerHTML = `<strong>Tip:</strong> Select your starting chips and click "Join Table" (need 2 more)`;
            } else {
                this.playerInfo.innerHTML = `<strong>Tip:</strong> Need ${needed} more player${needed > 1 ? 's' : ''} to start`;
            }
            this.playerInfo.className = 'info-text warning';
            this.startHandBtn.disabled = true;
            this.handInfo.textContent = `Requires 2+ players (${seatedPlayers}/2)`;
            this.handInfo.className = 'info-text';
        }
        
        // Step 3: Hand started
        if (street && street !== 'WAITING') {
            step3.classList.add('active');
            this.helpMessage.classList.add('hidden');
        } else {
            step3.classList.remove('active');
            if (seatedPlayers >= 2) {
                this.helpMessage.classList.remove('hidden');
            }
        }
    }

    async startHand() {
        // Check if we have enough players (client-side validation)
        const state = await this.getCurrentState();
        // Count seated players (any non-null seat) - before hand starts, status might be OUT
        const seatedPlayers = state.seats ? state.seats.filter(s => s !== null).length : 0;
        
        if (seatedPlayers < 2) {
            alert('Need at least 2 players seated to start a hand');
            return;
        }
        
        if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
            alert('Please connect to a table first');
            return;
        }
        
        // Auto-generate hand ID and use default seed
        const handId = `hand-${this.tableId}-${Date.now()}`;
        const seedCommit = 'abc123'; // Default seed for simplicity
        
        const command = {
            type: 'start_hand',
            data: {
                hand_id: handId,
                seed_commit: seedCommit
            },
            idempotency_key: `start-${handId}`,
            expected_version: this.expectedVersion
        };
        
        console.log('[UI] Starting hand:', handId);
        this.sendCommand(command);
    }
    
    async getCurrentState() {
        // Use last state from WebSocket if available (more reliable than REST API)
        if (this.lastState) {
            console.log('[UI] Using cached state from WebSocket');
            return this.lastState;
        }
        
        // Fallback to REST API if no WebSocket state yet
        try {
            const headers = {};
            if (this.token) {
                headers['Authorization'] = `Bearer ${this.token}`;
            }
            const response = await fetch(`${this.baseUrl}/api/v1/tables/${this.tableId}/snapshot`, {
                headers
            });
            if (!response.ok) {
                console.warn('[UI] REST API failed, returning empty state');
                return { seats: Array(9).fill(null) };
            }
            const state = await response.json();
            this.lastState = state; // Cache it
            return state;
        } catch (error) {
            console.warn('[UI] Error fetching state, returning empty state');
            return { seats: Array(9).fill(null) };
        }
    }

    async act(actionType) {
        if (this.currentSeat === null) {
            alert('You are not seated or it is not your turn');
            return;
        }
        
        let amount = null;
        if (actionType === 'BET' || actionType === 'RAISE') {
            amount = parseInt(this.betAmountInput.value);
            if (isNaN(amount) || amount <= 0) {
                alert('Please enter a valid bet amount');
                return;
            }
        }
        
        const command = {
            type: 'act',
            data: {
                seat_id: this.currentSeat,
                action_type: actionType,
                amount: amount
            },
            idempotency_key: `act-${Date.now()}`,
            expected_version: this.expectedVersion
        };
        
        this.sendCommand(command);
    }

    sendCommand(command) {
        if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
            alert('Not connected to server. Please connect first.');
            return;
        }
        
        this.ws.send(JSON.stringify(command));
        this.log('Sent command:', command.type);
    }
    
    handleError(error) {
        if (error.message && error.message.includes('Need at least 2 active players')) {
            alert('Need at least 2 players seated to start a hand. Please sit down more players first.');
        } else {
            alert('Error: ' + (error.message || error));
        }
    }

    addToHistory(event) {
        if (this.handHistory.querySelector('.empty')) {
            this.handHistory.innerHTML = '';
        }
        
        const eventEl = document.createElement('div');
        eventEl.className = 'event';
        
        // Clean event type name (remove camelCase)
        const eventType = event.event_type.replace(/([A-Z])/g, ' $1').trim();
        const time = new Date(event.timestamp * 1000).toLocaleTimeString('en-US', { 
            hour: '2-digit', 
            minute: '2-digit',
            second: '2-digit',
            hour12: false 
        });
        
        eventEl.innerHTML = `
            <strong>${eventType}</strong>
            <small>${time}</small>
        `;
        
        this.handHistory.insertBefore(eventEl, this.handHistory.firstChild);
        
        // Limit to 20 events
        while (this.handHistory.children.length > 20) {
            this.handHistory.removeChild(this.handHistory.lastChild);
        }
    }

    log(...args) {
        // Silent logging - only log errors in production
        if (args[0] && args[0].includes && args[0].includes('error')) {
            console.error('[PokerUI]', ...args);
        }
    }
}

// Initialize when page loads
document.addEventListener('DOMContentLoaded', () => {
    window.pokerUI = new PokerUI();
});

