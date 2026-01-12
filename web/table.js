// Poker Engine Web UI
class PokerUI {
    constructor() {
        this.ws = null;
        this.token = localStorage.getItem('auth_token');
        this.playerId = localStorage.getItem('player_id') || null;
        this.username = localStorage.getItem('username') || null;
        this.tableId = null; // Will be set when finding/creating table
        this.playerChips = 1000; // Default, will be loaded from API
        this.currentSeat = null;
        this.expectedVersion = 0;
        const protocol = window.location.protocol === 'https:' ? 'https:' : 'http:';
        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const host = window.location.host;
        this.baseUrl = `${protocol}//${host}`;
        this.wsUrl = `${wsProtocol}//${host}`;
        
        if (!this.token || !this.playerId) {
            window.location.href = 'login.html';
            return;
        }
        
        this.initializeElements();
        this.attachEventListeners();
        this.updateUserDisplay();
        this.loadPlayerChips();
    }

    initializeElements() {
        this.tableNameEl = document.getElementById('tableName');
        this.playersRow = document.getElementById('playersRow');
        this.communityCards = document.getElementById('communityCards');
        this.potDisplay = document.getElementById('potDisplay');
        this.potValueEl = document.getElementById('potValue');
        this.actionCenter = document.getElementById('actionCenter');
        this.waitBtn = document.getElementById('waitBtn');
        this.startHandBtn = document.getElementById('startHandBtn');
        this.actionPanel = document.getElementById('actionPanel');
        this.foldBtn = document.getElementById('foldBtn');
        this.checkBtn = document.getElementById('checkBtn');
        this.callBtn = document.getElementById('callBtn');
        this.betBtn = document.getElementById('betBtn');
        this.raiseBtn = document.getElementById('raiseBtn');
        this.betAmountInput = document.getElementById('betAmount');
        this.actionInfo = document.getElementById('actionInfo');
        this.yourCards = document.getElementById('yourCards');
        this.playerAvatar = document.getElementById('playerAvatar');
        this.playerStack = document.getElementById('playerStack');
        this.debugPanel = document.getElementById('debugPanel');
        this.debugContent = document.getElementById('debugContent');
        this.resultsPanel = document.getElementById('resultsPanel');
        this.resultsContent = document.getElementById('resultsContent');
        this.newHandBtn = document.getElementById('newHandBtn');
        this.leaveTableBtn = document.getElementById('leaveTableBtn');
        this.debugEnabled = false;
        this.lastState = null;
    }
    
    toggleDebug() {
        this.debugEnabled = !this.debugEnabled;
        if (this.debugPanel) {
            this.debugPanel.style.display = this.debugEnabled ? 'block' : 'none';
        }
    }
    
    debugState(state) {
        if (!this.debugEnabled || !this.debugContent) return;
        const mySeat = state.seats?.find(s => s?.player_id === this.playerId);
        const myCards = mySeat?.hole_cards || null;
        const allSeats = state.seats?.map((s, idx) => ({
            seat: idx,
            player_id: s?.player_id,
            has_cards: !!s?.hole_cards,
            cards: s?.hole_cards
        })) || [];
        this.debugContent.innerHTML = `
            <div style="margin-bottom: 8px;"><strong>My Player ID:</strong> ${this.playerId || 'null'}</div>
            <div style="margin-bottom: 8px;"><strong>My Seat:</strong> ${mySeat ? `Seat ${mySeat.seat_id} (${mySeat.player_id})` : 'Not seated'}</div>
            <div style="margin-bottom: 8px;"><strong>My Cards:</strong> ${myCards ? JSON.stringify(myCards, null, 2) : 'None'}</div>
            <div style="margin-bottom: 8px;"><strong>All Seats:</strong></div>
            <pre style="font-size: 10px; overflow: auto; max-height: 150px;">${JSON.stringify(allSeats, null, 2)}</pre>
            <div style="margin-top: 8px; font-size: 9px; color: #aaa;">Raw State:</div>
            <pre style="font-size: 9px; overflow: auto; max-height: 100px; color: #aaa;">${JSON.stringify(state, null, 2).substring(0, 500)}...</pre>
        `;
    }

    attachEventListeners() {
        if (this.foldBtn) this.foldBtn.addEventListener('click', () => this.act('FOLD', 0));
        if (this.checkBtn) this.checkBtn.addEventListener('click', () => this.act('CHECK', 0));
        if (this.callBtn) this.callBtn.addEventListener('click', () => this.call());
        if (this.betBtn) this.betBtn.addEventListener('click', () => this.bet());
        if (this.raiseBtn) this.raiseBtn.addEventListener('click', () => this.raise());
        
        // Start hand button is already attached via onclick in HTML
        this.connect();
    }

    updateUserDisplay() {
        if (this.tableNameEl) {
            this.tableNameEl.textContent = this.tableId;
        }
        if (this.playerAvatar) {
            this.playerAvatar.textContent = this.getAvatarEmoji(this.username || this.playerId);
        }
    }
    
    getAvatarEmoji(name) {
        if (!name) return '👤';
        const avatars = ['👤', '😊', '😎', '🤓', '😄', '🙂', '😃', '😁'];
        let hash = 0;
        for (let i = 0; i < name.length; i++) {
            hash = name.charCodeAt(i) + ((hash << 5) - hash);
        }
        return avatars[Math.abs(hash) % avatars.length];
    }

    logout() {
        localStorage.removeItem('auth_token');
        localStorage.removeItem('player_id');
        localStorage.removeItem('username');
        window.location.href = 'login.html';
    }

    async connect() {
        if (!this.token || !this.playerId) {
            window.location.href = 'login.html';
            return;
        }
        
        try {
            // Find or create a table (max 6 players)
            const response = await fetch(`${this.baseUrl}/api/v1/tables/find-or-create`, {
                headers: {
                    'Authorization': `Bearer ${this.token}`
                }
            });
            
            if (response.status === 401) {
                // Token expired or invalid, redirect to login
                console.log('[UI] Token expired, redirecting to login');
                this.logout();
                return;
            }
            
            if (!response.ok) {
                throw new Error('Failed to find or create table');
            }
            
            const data = await response.json();
            this.tableId = data.table_id;
            
            if (this.tableNameEl) {
                this.tableNameEl.textContent = this.tableId;
            }
            
            console.log(`[UI] ${data.action} table: ${this.tableId}`);
            
            // Connect to WebSocket
            const tokenParam = this.token ? `?token=${encodeURIComponent(this.token)}` : '';
            const wsUrl = `${this.wsUrl}/ws/tables/${this.tableId}${tokenParam}`;
            this.ws = new WebSocket(wsUrl);
            
            this.ws.onopen = () => {
                console.log('[UI] WebSocket connected');
            };
            this.ws.onmessage = (event) => {
                try {
                    this.handleMessage(JSON.parse(event.data));
                } catch (e) {
                    console.error('[UI] Error parsing message:', e);
                }
            };
            this.ws.onerror = () => {};
            this.ws.onclose = () => {};
        } catch (error) {
            console.error('[UI] Connection error:', error);
            alert('Failed to connect to table. Please try again.');
        }
    }


    handleMessage(data) {
        if (data.type === 'state') {
            this.lastState = data.data;
            this.debugState(data.data);
            this.updateTableState(data.data);
            if (data.version !== undefined) this.expectedVersion = data.version;
            
            // Auto-join only if NOT in an active hand and not already seated
            const isHandActive = this.lastState && 
                this.lastState.street && 
                this.lastState.street !== 'WAITING' && 
                this.lastState.street !== 'COMPLETE';
            const isSeated = this.lastState && this.lastState.seats?.some(s => s?.player_id === this.playerId);
            
            if (!isHandActive && !isSeated) {
                console.log('[UI] Auto-joining table (hand not active, player not seated)');
                // Small delay to avoid race conditions when multiple players join simultaneously
                setTimeout(() => {
                    // Re-check conditions after delay (state might have changed)
                    const currentState = this.lastState || this.getCurrentState();
                    const stillNotSeated = !currentState.seats?.some(s => s?.player_id === this.playerId);
                    const stillNotActive = !currentState.street || 
                        currentState.street === 'WAITING' || 
                        currentState.street === 'COMPLETE';
                    if (stillNotSeated && stillNotActive) {
                        this.joinTable();
                    }
                }, 100);
            } else if (isHandActive && !isSeated) {
                console.log('[UI] Cannot auto-join: hand is active (street:', this.lastState?.street, ') and player not seated');
                // Silently fail - player can't join during active hand
            } else if (isSeated) {
                console.log('[UI] Player already seated, skipping auto-join');
            }
        } else if (data.type === 'command_accepted') {
            console.log(`[UI] Command accepted: idempotency_key=${data.idempotency_key}, new_version=${data.new_version}`);
            if (data.new_version !== undefined) {
                this.expectedVersion = data.new_version;
            }
        } else if (data.type === 'error') {
            console.error(`[UI] Error from server: ${data.message}`);
            this.handleError({ message: data.message });
        } else {
            console.warn(`[UI] Unknown message type: ${data.type}`, data);
        }
    }


    updateTableState(state) {
        console.log('[UI] updateTableState called with state:', {
            street: state.street,
            hand_id: state.hand_id,
            seats_count: state.seats?.length,
            seats_with_cards: state.seats?.filter(s => s?.hole_cards?.length > 0).length,
            myPlayerId: this.playerId,
            to_act_seat: state.to_act_seat,
            current_bet: state.current_bet,
            pots_count: state.pots?.length,
            community_cards_count: state.community_cards?.length || 0,
            community_cards: state.community_cards
        });
        this.updateStreetDisplay(state.street);
        this.updatePlayersRow(state);
        this.updateCommunityCards(state.community_cards || []);
        this.updatePots(state.pots || [], state);
        this.updateYourCards(state);
        this.updatePlayerStack(state);
        this.updateResults(state);
        this.updateActions(state);
    }
    
    updateStreetDisplay(street) {
        // Update street display if element exists, or create it
        let streetEl = document.getElementById('streetDisplay');
        if (!streetEl) {
            // Create street display element
            const communityArea = document.querySelector('.community-area');
            if (communityArea) {
                streetEl = document.createElement('div');
                streetEl.id = 'streetDisplay';
                streetEl.className = 'street-display';
                communityArea.insertBefore(streetEl, communityArea.firstChild);
            } else {
                return;
            }
        }
        
        if (!street) {
            streetEl.textContent = '';
            streetEl.style.display = 'none';
            return;
        }
        
        const streetNames = {
            'WAITING': 'Waiting',
            'PREFLOP': 'Pre-Flop',
            'FLOP': 'Flop',
            'TURN': 'Turn',
            'RIVER': 'River',
            'SHOWDOWN': 'Showdown',
            'COMPLETE': 'Complete'
        };
        
        streetEl.textContent = streetNames[street] || street;
        streetEl.style.display = 'block';
    }
    
    updatePlayersRow(state) {
        if (!this.playersRow) return;
        
        this.playersRow.innerHTML = '';
        const seats = (state.seats || []).filter(s => s !== null);
        
        seats.forEach(seat => {
            const playerItem = document.createElement('div');
            playerItem.className = 'player-item';
            
            const isToAct = state.to_act_seat === seat.seat_id;
            const isActive = seat.status === 'ACTIVE' || seat.status === 'ALL_IN';
            const isAllIn = seat.status === 'ALL_IN';
            const avatar = this.getAvatarEmoji(seat.player_id);
            const shortName = (seat.player_id || `Player${seat.seat_id + 1}`).replace('player_', '').substring(0, 10);
            const betBadge = seat.committed_total > 0 ? `<div class="player-bet">${seat.committed_total}</div>` : '';
            const allInBadge = isAllIn ? '<div class="player-allin">ALL IN</div>' : '';
            
            playerItem.innerHTML = `
                ${betBadge}
                ${allInBadge}
                <div class="player-avatar ${isActive ? 'active' : ''} ${isToAct ? 'to-act' : ''} ${isAllIn ? 'all-in' : ''}">${avatar}</div>
                <div class="player-name">${shortName}</div>
                <div class="player-score">${seat.stack}</div>
            `;
            
            this.playersRow.appendChild(playerItem);
        });
    }
    
    updatePlayerStack(state) {
        const mySeat = state.seats?.find(s => s?.player_id === this.playerId);
        if (mySeat?.stack && this.playerStack) {
            this.playerStack.textContent = mySeat.stack.toLocaleString();
        }
    }
    
    updateResults(state) {
        if (!this.resultsPanel || !this.resultsContent) return;
        
        const results = state.last_hand_results;
        const street = state.street || 'WAITING';
        
        // Show results panel if we have results and hand is waiting (just completed)
        if (results && Object.keys(results).length > 0 && street === 'WAITING') {
            console.log('[UI] Displaying hand results:', results);
            
            // Build results display
            let resultsHTML = '<div class="results-winners">';
            const winnerCount = Object.keys(results).length;
            
            if (winnerCount === 1) {
                // Single winner
                const [seatIdStr, amount] = Object.entries(results)[0];
                const seatId = parseInt(seatIdStr);
                const seat = state.seats?.[seatId];
                const playerName = seat?.player_id ? seat.player_id.replace('player_', '') : `Seat ${seatId + 1}`;
                const isMe = seat?.player_id === this.playerId;
                
                resultsHTML += `
                    <div class="winner-announcement ${isMe ? 'you-win' : ''}">
                        <div class="winner-label">${isMe ? '🎉 You Win!' : '🏆 Winner'}</div>
                        <div class="winner-name">${playerName}</div>
                        <div class="winner-amount">$${amount.toLocaleString()}</div>
                    </div>
                `;
            } else {
                // Split pot (multiple winners)
                resultsHTML += '<div class="winner-label">💰 Split Pot</div>';
                resultsHTML += '<div class="winners-list">';
                
                for (const [seatIdStr, amount] of Object.entries(results)) {
                    const seatId = parseInt(seatIdStr);
                    const seat = state.seats?.[seatId];
                    const playerName = seat?.player_id ? seat.player_id.replace('player_', '') : `Seat ${seatId + 1}`;
                    const isMe = seat?.player_id === this.playerId;
                    
                    resultsHTML += `
                        <div class="winner-item ${isMe ? 'you-win' : ''}">
                            <div class="winner-name">${isMe ? '👤 You' : playerName}</div>
                            <div class="winner-amount">$${amount.toLocaleString()}</div>
                        </div>
                    `;
                }
                
                resultsHTML += '</div>';
            }
            
            resultsHTML += '</div>';
            this.resultsContent.innerHTML = resultsHTML;
            
            // Show results panel, hide action center and action panel
            this.resultsPanel.style.display = 'flex';
            if (this.actionCenter) this.actionCenter.style.display = 'none';
            if (this.actionPanel) this.actionPanel.style.display = 'none';
        } else {
            // Hide results panel if no results or hand is active
            this.resultsPanel.style.display = 'none';
        }
    }
    
    updateActions(state) {
        const mySeat = state.seats?.find(s => s?.player_id === this.playerId);
        const street = state.street || 'WAITING';
        const isHandActive = street !== 'WAITING' && street !== 'COMPLETE';
        const hasResults = state.last_hand_results && Object.keys(state.last_hand_results).length > 0;
        const canAct = isHandActive && mySeat && mySeat.status === 'ACTIVE' && state.to_act_seat === mySeat.seat_id;
        
        // Show start hand button if waiting (with or without results) and seated
        const seatedCount = state.seats.filter(s => s && s.player_id).length;
        const canStartHand = !isHandActive && mySeat && seatedCount >= 2;
        
        console.log(`[UI] updateActions: street=${street}, isHandActive=${isHandActive}, canAct=${canAct}, canStartHand=${canStartHand}, hasResults=${hasResults}, seatedCount=${seatedCount}, mySeat=${!!mySeat}`);
        
        // If results are showing, hide action center and action panel
        // Results panel has its own buttons (Start New Hand, Leave Table)
        if (hasResults && street === 'WAITING') {
            if (this.actionPanel) this.actionPanel.style.display = 'none';
            if (this.actionCenter) this.actionCenter.style.display = 'none';
            return;
        }
        
        if (canAct) {
            // Player's turn - show action panel
            this.currentSeat = mySeat.seat_id;
            if (this.actionPanel) {
                this.actionPanel.style.display = 'block';
                this.updateActionButtons(state, mySeat);
            }
            if (this.actionCenter) this.actionCenter.style.display = 'none';
            if (this.resultsPanel) this.resultsPanel.style.display = 'none';
        } else {
            // Not player's turn
            this.currentSeat = null;
            if (this.actionPanel) this.actionPanel.style.display = 'none';
            
            if (this.actionCenter) {
                this.actionCenter.style.display = 'flex';
                
                if (canStartHand) {
                    // Show start hand button
                    console.log('[UI] Showing start hand button');
                    if (this.startHandBtn) {
                        this.startHandBtn.style.display = 'block';
                        this.startHandBtn.disabled = false;
                    }
                    if (this.waitBtn) {
                        this.waitBtn.style.display = 'none';
                    }
                } else if (!isHandActive) {
                    // Show wait message
                    if (this.startHandBtn) {
                        this.startHandBtn.style.display = 'none';
                    }
                    if (this.waitBtn) {
                        this.waitBtn.style.display = 'block';
                        this.waitBtn.textContent = seatedCount < 2 ? 'Waiting for players...' : 'Wait for the next hand';
                        this.waitBtn.disabled = true;
                    }
                } else {
                    // Hand is active but not player's turn
                    if (this.startHandBtn) {
                        this.startHandBtn.style.display = 'none';
                    }
                    if (this.waitBtn) {
                        this.waitBtn.style.display = 'block';
                        this.waitBtn.textContent = 'Wait for your turn';
                        this.waitBtn.disabled = true;
                    }
                }
            }
            
            // Hide results panel if hand is active or no results
            if (this.resultsPanel && (isHandActive || !hasResults)) {
                this.resultsPanel.style.display = 'none';
            }
        }
    }

    updateYourCards(state) {
        if (!this.yourCards) return;
        
        const mySeat = state.seats?.find(s => s && s.player_id === this.playerId);
        this.yourCards.innerHTML = '';
        
        console.log('[UI] updateYourCards:', {
            hasMySeat: !!mySeat,
            myPlayerId: this.playerId,
            seatPlayerId: mySeat?.player_id,
            hasHoleCards: !!mySeat?.hole_cards,
            holeCardsLength: mySeat?.hole_cards?.length,
            holeCards: mySeat?.hole_cards
        });
        
        if (mySeat?.hole_cards?.length === 2) {
            console.log('[UI] Rendering hole cards:', mySeat.hole_cards);
            mySeat.hole_cards.forEach((card, idx) => {
                console.log(`[UI] Creating card element ${idx}:`, card);
                const cardEl = this.createCardElement(card);
                console.log(`[UI] Card element ${idx} created:`, cardEl);
                if (cardEl) {
                    this.yourCards.appendChild(cardEl);
                } else {
                    console.error(`[UI] Failed to create card element for card ${idx}:`, card);
                }
            });
        } else {
            console.log('[UI] No hole cards, showing card backs');
            for (let i = 0; i < 2; i++) {
                const cardBack = document.createElement('div');
                cardBack.className = 'card-back';
                this.yourCards.appendChild(cardBack);
            }
        }
    }

    updateCommunityCards(cards) {
        if (!this.communityCards) return;
        
        console.log('[UI] updateCommunityCards called with cards:', cards, 'count:', cards?.length);
        
        this.communityCards.innerHTML = '';
        if (!cards || !Array.isArray(cards) || cards.length === 0) {
            console.log('[UI] No community cards to display');
            return;
        }
        
        cards.forEach((card, index) => {
            const cardEl = this.createCardElement(card);
            if (cardEl) {
                this.communityCards.appendChild(cardEl);
                console.log(`[UI] Added community card ${index + 1}:`, card);
            } else {
                console.error(`[UI] Failed to create card element for card ${index + 1}:`, card);
            }
        });
        
        console.log('[UI] Community cards updated, total cards:', this.communityCards.children.length);
    }

    createCardElement(card) {
        if (typeof card !== 'object' || card === null) {
            console.error('[UI] createCardElement: card is not an object:', card);
            return null;
        }
        
        console.log('[UI] createCardElement: processing card:', card);
        
        const rankValue = typeof card.rank === 'object' && card.rank?.value !== undefined 
            ? card.rank.value 
            : typeof card.rank === 'number' 
                ? card.rank 
                : parseInt(card.rank?.value || card.rank?.name || card.rank || 0);
        
        const suitValue = typeof card.suit === 'object' && card.suit?.value !== undefined
            ? card.suit.value
            : typeof card.suit === 'number'
                ? card.suit
                : parseInt(card.suit?.value || card.suit?.name || card.suit || 0);
        
        console.log('[UI] createCardElement: extracted rankValue=', rankValue, 'suitValue=', suitValue);
        
        if (typeof rankValue !== 'number' || isNaN(rankValue) || typeof suitValue !== 'number' || isNaN(suitValue)) {
            console.error('[UI] createCardElement: invalid rank/suit values:', { rankValue, suitValue, card });
            return null;
        }
        
        if (rankValue < 2 || rankValue > 14 || suitValue < 0 || suitValue > 3) {
            console.error('[UI] createCardElement: rank/suit out of range:', { rankValue, suitValue });
            return null;
        }
        
        const cardEl = document.createElement('div');
        const rank = this.getRankSymbol(rankValue);
        const suit = this.getSuitSymbol(suitValue);
        const isRed = suitValue === 1 || suitValue === 2;
        
        cardEl.className = `card ${isRed ? 'red' : 'black'}`;
        cardEl.innerHTML = `
            <div class="card-rank">${rank}</div>
            <div class="card-suit">${suit}</div>
        `;
        
        console.log('[UI] createCardElement: created card element:', { rank, suit, isRed, className: cardEl.className });
        
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

    updatePots(pots, state) {
        // Calculate pot from pots array if available, otherwise from committed_total
        let totalPot = pots?.reduce((sum, pot) => sum + (pot.amount || 0), 0) || 0;
        
        // If pots array is empty but hand is active, calculate from committed_total
        if (totalPot === 0 && state && state.street !== 'WAITING' && state.street !== 'COMPLETE') {
            totalPot = (state.seats || []).reduce((sum, seat) => {
                if (seat && seat.committed_total) {
                    return sum + (seat.committed_total || 0);
                }
                return sum;
            }, 0);
        }
        
        if (this.potValueEl) this.potValueEl.textContent = `$${totalPot}`;
        if (this.potDisplay) this.potDisplay.style.display = 'flex';
    }

    updateActionButtons(state, seat) {
        if (!this.actionInfo || !this.foldBtn || !this.checkBtn || !this.callBtn || !this.betBtn || !this.raiseBtn) return;
        
        const callAmount = Math.max(0, (state.current_bet || 0) - (seat.committed_street || 0));
        const minBet = state.big_blind || 100;
        const minRaiseIncrement = state.min_raise || state.big_blind || 100;
        const minRaiseTotal = callAmount + minRaiseIncrement;
        const hasBet = state.current_bet > 0;
        
        this.actionInfo.innerHTML = `
            <div style="font-size: 13px; margin-bottom: 8px;">
                <strong>Stack:</strong> ${seat.stack} · 
                <strong>Current Bet:</strong> ${state.current_bet || 0} · 
                <strong>To Call:</strong> ${callAmount}
            </div>
            <div style="font-size: 11px; color: var(--text-tertiary);">
                ${hasBet ? `Min Raise: ${minRaiseIncrement} (total: ${minRaiseTotal})` : `Min Bet: ${minBet}`}
            </div>
        `;
        
        // Fold is always available (can always fold)
        this.foldBtn.disabled = false;
        
        // Check is available when no bet to call (callAmount === 0)
        this.checkBtn.disabled = callAmount > 0;
        
        // Call is available when there's a bet to call (callAmount > 0) and player has stack
        this.callBtn.disabled = callAmount === 0 || seat.stack === 0;
        this.callBtn.textContent = callAmount > 0 ? `Call ${Math.min(callAmount, seat.stack)}` : 'Call';
        
        // Bet is available when no bet exists (current_bet === 0) and player has stack
        this.betBtn.disabled = hasBet || seat.stack === 0;
        
        // Raise is available when a bet exists (current_bet > 0) and player has stack
        this.raiseBtn.disabled = !hasBet || seat.stack === 0;
        
        if (this.betAmountInput) {
            if (hasBet) {
                this.betAmountInput.min = minRaiseTotal;
                this.betAmountInput.max = seat.stack;
                this.betAmountInput.placeholder = `Raise to (${minRaiseTotal}-${seat.stack})`;
                this.betAmountInput.value = minRaiseTotal;
            } else {
                this.betAmountInput.min = minBet;
                this.betAmountInput.max = seat.stack;
                this.betAmountInput.placeholder = `Bet (${minBet}-${seat.stack})`;
                this.betAmountInput.value = minBet;
            }
        }
    }

    async joinTable() {
        if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
            console.log('[UI] Cannot join: WebSocket not open');
            return;
        }
        
        const state = this.lastState || this.getCurrentState();
        if (!state?.seats) {
            console.log('[UI] Cannot join: No state available');
            return;
        }
        
        // Don't join if hand is active - players must be seated before hand starts
        const isHandActive = state.street && 
            state.street !== 'WAITING' && 
            state.street !== 'COMPLETE';
        if (isHandActive) {
            console.log('[UI] Cannot join: Hand is active (street:', state.street, ') - players must be seated before hand starts');
            return;
        }
        
        // Already seated
        if (state.seats.some(s => s?.player_id === this.playerId)) {
            console.log('[UI] Already seated, skipping join');
            return;
        }
        
        // Check if table is full (6 players max)
        const seatedCount = state.seats.filter(s => s && s.player_id).length;
        if (seatedCount >= 6) {
            console.warn('[UI] Table is full (6 players max), redirecting to find new table');
            // Reconnect to find/create a new table
            this.connect();
            return;
        }
        
        const seatId = this.findNextAvailableSeat(state);
        if (seatId === null || seatId === -1) {
            console.warn('[UI] No available seats');
            this.handleError({ message: 'No available seats at this table' });
            return;
        }
        
        console.log(`[UI] Joining table at seat ${seatId} with ${this.playerChips} chips`);
        this.sendCommand({
            type: 'sit_down',
            data: {
                seat_id: seatId,
                stack: this.playerChips,
                player_id: this.playerId
            },
            idempotency_key: `join-${this.playerId}-${Date.now()}`,
            expected_version: this.expectedVersion
        });
    }
    
    async loadPlayerChips() {
        try {
            const response = await fetch(`${this.baseUrl}/api/v1/players/me`, {
                headers: {
                    'Authorization': `Bearer ${this.token}`
                }
            });
            
            if (response.status === 401) {
                // Token expired or invalid, redirect to login
                console.log('[UI] Token expired, redirecting to login');
                this.logout();
                return;
            }
            
            if (response.ok) {
                const data = await response.json();
                this.playerChips = data.chips || 1000;
            }
        } catch (error) {
            console.error('[UI] Error loading player chips:', error);
            this.playerChips = 1000; // Default fallback
        }
    }
    
    

    async startHand() {
        if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
            console.error('[UI] WebSocket not connected');
            alert('Not connected to table. Please wait...');
            return;
        }
        const state = this.getCurrentState();
        if (!state) {
            console.error('[UI] No state available');
            return;
        }
        const seatedPlayers = state.seats.filter(s => s && s.player_id);
        if (seatedPlayers.length < 2) {
            alert('Need at least 2 players to start a hand');
            return;
        }
        
        // Hide results panel immediately when starting a new hand
        if (this.resultsPanel) {
            this.resultsPanel.style.display = 'none';
        }
        
        // Generate hand_id and seed_commit
        const handId = `hand-${this.tableId}-${Date.now()}`;
        const seedCommit = `seed-${Date.now()}-${Math.random().toString(36).substring(7)}`;
        
        console.log(`[UI] Starting hand: ${handId}`);
        
        this.sendCommand({
            type: 'start_hand',
            data: {
                hand_id: handId,
                seed_commit: seedCommit
            },
            idempotency_key: `start-${Date.now()}`,
            expected_version: this.expectedVersion
        });
    }
    
    async leaveTable() {
        // Get current stack from game state before leaving
        const state = this.getCurrentState();
        const mySeat = state?.seats?.find(s => s?.player_id === this.playerId);
        
        if (mySeat && mySeat.stack !== undefined && mySeat.stack >= 0) {
            const currentStack = mySeat.stack;
            console.log(`[UI] Leaving table with stack: ${currentStack} (original when joined: ${this.playerChips})`);
            
            try {
                // Set chips to current stack value (absolute, not relative)
                // This is a backup - chips should already be updated when hand ends, but update again to be safe
                const response = await fetch(`${this.baseUrl}/api/v1/players/set-chips?chips=${currentStack}`, {
                    method: 'POST',
                    headers: {
                        'Authorization': `Bearer ${this.token}`,
                        'Content-Type': 'application/json'
                    }
                });
                
                if (response.ok) {
                    const data = await response.json();
                    console.log(`[UI] Chips updated successfully: ${data.chips}`);
                } else {
                    const errorText = await response.text();
                    console.error('[UI] Failed to update chips:', response.status, errorText);
                    // Still continue with redirect even if update fails
                }
            } catch (error) {
                console.error('[UI] Error updating chips:', error);
                // Continue with redirect even if update fails
            }
        } else {
            console.log('[UI] Could not find seat or invalid stack, skipping chip update (chips may already be updated from hand completion)');
        }
        
        // Close WebSocket connection and redirect to home
        console.log('[UI] Leaving table, redirecting to home');
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.close();
        }
        // Wait a small delay to ensure any pending requests complete
        await new Promise(resolve => setTimeout(resolve, 100));
        window.location.href = 'home.html';
    }
    
    getCurrentState() {
        return this.lastState || { seats: Array(9).fill(null), street: 'WAITING', current_bet: 0, pots: [] };
    }
    
    findNextAvailableSeat(state) {
        const seats = state.seats || [];
        // Count seated players - max 6 per table
        const seatedCount = seats.filter(s => s && s.player_id).length;
        if (seatedCount >= 6) {
            console.log('[UI] Table is full (6 players max), should create new table');
            return null; // Table is full
        }
        
        // Find first empty seat (None/null) or seat with no player_id
        // Limit to 6 seats total (max 6 players per table)
        for (let i = 0; i < Math.min(6, seats.length || 6); i++) {
            const seat = seats[i];
            if (!seat || !seat.player_id) {
                return i;
            }
        }
        return null;
    }

    async act(actionType, amount = null) {
        if (!this.lastState || this.currentSeat === null) {
            alert('Not your turn or game state unavailable');
            return;
        }
        
        const mySeat = this.lastState.seats?.find(s => s?.player_id === this.playerId);
        if (!mySeat) return;
        
        this.sendCommand({
            type: 'act',
            data: {
                seat_id: mySeat.seat_id,
                action_type: actionType,
                amount: amount
            },
            idempotency_key: `act-${Date.now()}-${Math.random()}`,
            expected_version: this.expectedVersion
        });
    }
    
    call() {
        const mySeat = this.lastState?.seats?.find(s => s?.player_id === this.playerId);
        if (!mySeat) {
            console.error('[UI] Cannot call: player not seated');
            return;
        }
        const callAmount = Math.max(0, (this.lastState.current_bet || 0) - (mySeat.committed_street || 0));
        if (callAmount === 0) {
            console.warn('[UI] Call button clicked but no bet to call - this should be disabled');
            return;
        }
        if (callAmount > mySeat.stack) {
            alert('Call amount exceeds your stack');
            return;
        }
        console.log(`[UI] Calling ${callAmount} (current_bet=${this.lastState.current_bet}, committed_street=${mySeat.committed_street})`);
        // Call amount is calculated automatically by backend (amount is null for CALL)
        this.act('CALL', null);
    }
    
    bet() {
        const amount = this._getBetAmount();
        const mySeat = this.lastState?.seats?.find(s => s?.player_id === this.playerId);
        if (!amount || !mySeat || amount > mySeat.stack) {
            alert(`Bet exceeds your stack (${mySeat?.stack || 0})`);
            return;
        }
        const minBet = this.lastState.big_blind || 100;
        if (amount < minBet) {
            alert(`Bet must be at least ${minBet}`);
            return;
        }
        this.act('BET', amount);
    }
    
    raise() {
        const amount = this._getBetAmount();
        const mySeat = this.lastState?.seats?.find(s => s?.player_id === this.playerId);
        if (!amount || !mySeat || amount > mySeat.stack) {
            alert(`Raise exceeds your stack (${mySeat?.stack || 0})`);
            return;
        }
        const callAmount = Math.max(0, (this.lastState.current_bet || 0) - (mySeat.committed_street || 0));
        const minRaiseTotal = callAmount + (this.lastState.min_raise || this.lastState.big_blind || 100);
        if (amount < minRaiseTotal) {
            alert(`Raise must be at least ${minRaiseTotal}`);
            return;
        }
        this.act('RAISE', amount);
    }
    
    _getBetAmount() {
        if (!this.betAmountInput || !this.lastState) return null;
        const amount = parseInt(this.betAmountInput.value);
        if (isNaN(amount) || amount <= 0) {
            alert('Please enter a valid amount');
            return null;
        }
        return amount;
    }

    sendCommand(command) {
        if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
            alert('Not connected to server');
            return;
        }
        this.ws.send(JSON.stringify(command));
    }
    
    handleError(error) {
        const message = error.message || error;
        if (message.includes('Need at least 2')) {
            alert('Need at least 2 players seated to start a hand');
        } else {
            alert('Error: ' + message);
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    window.pokerUI = new PokerUI();
});

