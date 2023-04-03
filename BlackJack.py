import sys
from random import shuffle

import numpy as np
import scipy.stats as stats
import pylab as pl
import matplotlib.pyplot as plt
import copy
import time
import sqlite3
from sqlite3 import Error

from importer.StrategyImporter import StrategyImporter


GAMES = 20000
SHOE_SIZE = 8
SHOE_PENETRATION = 0.5
BET_SPREAD = 20.0
BET_SPREAD_6 = 10.0
BET_SPREAD_5 = 5.0
BET_SPREAD_4 = 3.0
BET_SPREAD_3 = 2.0

DECK_SIZE = 52.0
CARDS = {"Ace": 11, "Two": 2, "Three": 3, "Four": 4, "Five": 5, "Six": 6, "Seven": 7, "Eight": 8, "Nine": 9, "Ten": 10, "Jack": 10, "Queen": 10, "King": 10}
BASIC_OMEGA_II = {"Ace": 0, "Two": 1, "Three": 1, "Four": 2, "Five": 2, "Six": 2, "Seven": 1, "Eight": 0, "Nine": -1, "Ten": -2, "Jack": -2, "Queen": -2, "King": -2}

BLACKJACK_RULES = {
    'triple7': False,  # Count 3x7 as a blackjack
}

STRATEGY = ""
HARD_STRATEGY = {}
SOFT_STRATEGY = {}
PAIR_STRATEGY = {}

DATABASE = ""
COUNT_DATABASE = 0

class Database:
    def __init__(self, path):
        self.count_database_searchs = 0
        self.create_connection(path)
        self.create_tables()

    def create_connection(self, path):
        try:
            self.connection = sqlite3.connect(path)
            #print("Connection to SQLite DB successful")
        except Error as e:
            print(f"The error '{e}' occurred")

    def execute_query(self, query):
        cursor = self.connection.cursor()
        try:
            cursor.execute(query)
            self.connection.commit()
            #print("Query executed successfully")
        except Error as e:
            print(f"The error '{e}' occurred")
        
    def select_table(self, query, arguments):
        cur = self.connection.cursor()
        #print("Select on table")
        cur.execute(query, arguments)
        self.connection.commit()
        return cur.fetchall()

    def create_tables(self):
        cur = self.connection.cursor()
        #print("Creating tables")

        cur.execute(
            """CREATE TABLE IF NOT EXISTS BLACKJACK_CHANCES(
                id integer PRIMARY KEY AUTOINCREMENT,
                dealer text NOT NULL,
                Ace integer NOT NULL,
                Two integer NOT NULL,
                Three integer NOT NULL,
                Four integer NOT NULL,
                Five integer NOT NULL,
                Six integer NOT NULL,
                Seven integer NOT NULL,
                Eight integer NOT NULL,
                Nine integer NOT NULL,
                Ten integer NOT NULL,
                Seventeen real NOT NULL,
                Eightteen real NOT NULL,
                Nineteen real NOT NULL,
                Twenty real NOT NULL,
                Twentyone real NOT NULL,
                Busted real NOT NULL,
                Winning_chance_hit real, 
                Winning_chance_stand real
                );""")

        self.connection.commit()
        
    def insert_update_table(self, query, arguments):
        cur = self.connection.cursor()
        cur.execute(query, arguments)
        self.connection.commit()
        #self.logger.info("Insert/Update on table successfully")

class Card(object):
    """
    Represents a playing card with name and value.
    """
    def __init__(self, name, value):
        self.name = name
        self.value = value

    def __str__(self):
        return "%s" % self.name


class Shoe(object):
    """
    Represents the shoe, which consists of a number of card decks.
    """
    reshuffle = False

    def __init__(self, decks):
        self.count = 0
        self.count_history = []
        self.ideal_count = {}
        self.decks = decks
        self.cards = self.init_cards()
        self.init_count()

    def __str__(self):
        s = ""
        for c in self.cards:
            s += "%s\n" % c
        return s

    def init_cards(self):
        """
        Initialize the shoe with shuffled playing cards and set count to zero.
        """
        self.count = 0
        self.count_history.append(self.count)

        cards = []
        for d in range(self.decks):
            for c in CARDS:
                for i in range(0, 4):
                    cards.append(Card(c, CARDS[c]))
        shuffle(cards)
        return cards

    def init_count(self):
        """
        Keep track of the number of occurrences for each card in the shoe in the course over the game. ideal_count
        is a dictionary containing (card name - number of occurrences in shoe) pairs
        """
        for card in CARDS:
            self.ideal_count[card] = 4 * SHOE_SIZE

    def deal(self):
        """
        Returns:    The next card off the shoe. If the shoe penetration is reached,
                    the shoe gets reshuffled.
        """
        if self.shoe_penetration() < SHOE_PENETRATION:
            self.reshuffle = True
        card = self.cards.pop()

        assert self.ideal_count[card.name] > 0, "Either a cheater or a bug!"
        self.ideal_count[card.name] -= 1

        self.do_count(card)
        return card

    def deal_card(self, card):
        """
        Returns:    The next card off the shoe. If the shoe penetration is reached,
                    the shoe gets reshuffled.
        """
        if self.shoe_penetration() < SHOE_PENETRATION:
            self.reshuffle = True

        assert self.ideal_count[card.name] > 0, "Either a cheater or a bug!"
        self.ideal_count[card.name] -= 1

        self.do_count(card)
        return card

    def total_card(self):
        total_cards = 0
        for card in CARDS:
            total_cards += self.ideal_count[card]
        return total_cards

    def do_count(self, card):
        """
        Add the dealt card to current count.
        """
        self.count += BASIC_OMEGA_II[card.name]
        self.count_history.append(self.truecount())

    def truecount(self):
        """
        Returns: The current true count.
        """
        return self.count / (self.decks * self.shoe_penetration())

    def shoe_penetration(self):
        """
        Returns: Ratio of cards that are still in the shoe to all initial cards.
        """
        return len(self.cards) / (DECK_SIZE * self.decks)


class Hand(object):
    """
    Represents a hand, either from the dealer or from the player
    """
    _value = 0
    _aces = []
    _aces_soft = 0
    splithand = False
    surrender = False
    doubled = False

    def __init__(self, cards):
        self.cards = cards

    def __str__(self):
        h = ""
        for c in self.cards:
            h += "%s " % c
        return h

    @property
    def value(self):
        """
        Returns: The current value of the hand (aces are either counted as 1 or 11).
        """
        self._value = 0
        for c in self.cards:
            self._value += c.value

        if self._value > 21 and self.aces_soft > 0:
            for ace in self.aces:
                if ace.value == 11:
                    self._value -= 10
                    ace.value = 1
                    if self._value <= 21:
                        break

        return self._value

    @property
    def aces(self):
        """
        Returns: The all aces in the current hand.
        """
        self._aces = []
        for c in self.cards:
            if c.name == "Ace":
                self._aces.append(c)
        return self._aces

    @property
    def aces_soft(self):
        """
        Returns: The number of aces valued as 11
        """
        self._aces_soft = 0
        for ace in self.aces:
            if ace.value == 11:
                self._aces_soft += 1
        return self._aces_soft

    def soft(self):
        """
        Determines whether the current hand is soft (soft means that it consists of aces valued at 11).
        """
        if self.aces_soft > 0:
            return True
        else:
            return False

    def splitable(self):
        """
        Determines if the current hand can be splitted.
        """
        if self.length() == 2 and self.cards[0].name == self.cards[1].name:
            return True
        else:
            return False

    def blackjack(self):
        """
        Check a hand for a blackjack, taking the defined BLACKJACK_RULES into account.
        """
        if not self.splithand and self.value == 21:
            if all(c.value == 7 for c in self.cards) and BLACKJACK_RULES['triple7']:
                return True
            elif self.length() == 2:
                return True
            else:
                return False
        else:
            return False

    def busted(self):
        """
        Checks if the hand is busted.
        """
        if self.value > 21:
            return True
        else:
            return False

    def add_card(self, card):
        """
        Add a card to the current hand.
        """
        self.cards.append(card)

    def split(self):
        """
        Split the current hand.
        Returns: The new hand created from the split.
        """
        self.splithand = True
        c = self.cards.pop()
        new_hand = Hand([c])
        new_hand.splithand = True
        return new_hand

    def length(self):
        """
        Returns: The number of cards in the current hand.
        """
        return len(self.cards)


class Player(object):
    """
    Represent a player
    """
    def __init__(self, hand=None, dealer_hand=None):
        self.hands = [hand]
        self.dealer_hand = dealer_hand

    def set_hands(self, new_hand, new_dealer_hand):
        self.hands = [new_hand]
        self.dealer_hand = new_dealer_hand

    def play_simulation(self, shoe, dealer):
        for hand in self.hands:
            # print "Playing Hand: %s" % hand
            self.play_hand_simulation_percentage(hand, shoe, dealer)

    def translate_card(self, card):
        if card == "1":
            card = "Ace"
        elif card == "2":
            card = "Two"
        elif card == "3":
            card = "Three"
        elif card == "4":
            card = "Four"
        elif card == "5":
            card = "Five"
        elif card == "6":
            card = "Six"
        elif card == "7":
            card = "Seven"
        elif card == "8":
            card = "Eight"
        elif card == "9":
            card = "Nine"
        elif card == "10":
            card = "Ten"
        elif card == "j":
            card = "Jack"
        elif card == "q":
            card = "Queen"
        elif card == "k":
            card = "King"
        return card

    def play_hand_simulation_percentage(self, hand, shoe, dealer):
        while not hand.busted() and not hand.blackjack():
            self.splitted = False
            if hand.soft():
                flag = SOFT_STRATEGY[hand.value][self.dealer_hand.cards[0].name]
            elif hand.splitable():
                flag = PAIR_STRATEGY[hand.value][self.dealer_hand.cards[0].name]
            else:
                flag = HARD_STRATEGY[hand.value][self.dealer_hand.cards[0].name]

            if flag == 'D':
                if hand.length() == 2:
                    print("Double Down")
                    hand.doubled = True
                    player_card = self.translate_card(input("Card from double\n"))
                    self.hit_card(hand, shoe, Card(player_card, CARDS[player_card]))
                    break
                else:
                    flag = 'H'

            if flag == 'P':
                print("Split")
                self.split_simulation(hand, shoe)
                self.splitted = True
            
            if not self.splitted:
                rows = DATABASE.select_table("""SELECT * FROM BLACKJACK_CHANCES WHERE dealer=? AND Ace=? AND Two=? AND Three=? AND Four=? AND Five=? AND Six=?
                    AND Seven=? AND Eight=? AND Nine=? AND Ten=?""", 
                    (dealer.hand.cards[0].name, shoe.ideal_count["Ace"], shoe.ideal_count["Two"], shoe.ideal_count["Three"],
                    shoe.ideal_count["Four"], shoe.ideal_count["Five"], shoe.ideal_count["Six"], shoe.ideal_count["Seven"],
                    shoe.ideal_count["Eight"], shoe.ideal_count["Nine"], shoe.ideal_count["Ten"] + shoe.ideal_count["Jack"] + shoe.ideal_count["Queen"] + shoe.ideal_count["King"]))

                winning_chance_hit = 0.0
                winning_chance_stand = 0.0
                if rows:
                    print("Chances already in database")
                    DATABASE.count_database_searchs += 1
                    winning_chance_hit = rows[0][18]
                    winning_chance_stand = rows[0][19]
                else:
                    self.player_possibilities = {"17": 0.0, "18": 0.0, "19": 0.0, "20": 0.0, "21": 0.0, "Busted": 0.0}
                    self.dealer_possibilities = {"17": 0.0, "18": 0.0, "19": 0.0, "20": 0.0, "21": 0.0, "Busted": 0.0}
                    self.calculate_percentage(dealer.hand, shoe, self.dealer_possibilities)
                    self.calculate_percentage(hand, shoe, self.player_possibilities)
                    self.bust_chance, self.not_bust_chance = self.player_percentage_bust(hand, shoe)
                    winning_chance_hit, winning_chance_stand = self.winning_chance_calc(hand)
                    DATABASE.insert_update_table("""INSERT INTO BLACKJACK_CHANCES (
                        dealer, Ace, Two, Three, Four, Five, Six, Seven, Eight, Nine, Ten, Seventeen, Eightteen, Nineteen, Twenty, Twentyone, Busted, Winning_chance_hit, Winning_chance_stand) 
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", 
                        (dealer.hand.cards[0].name, shoe.ideal_count["Ace"], shoe.ideal_count["Two"], shoe.ideal_count["Three"],
                        shoe.ideal_count["Four"], shoe.ideal_count["Five"], shoe.ideal_count["Six"], shoe.ideal_count["Seven"],
                        shoe.ideal_count["Eight"], shoe.ideal_count["Nine"], shoe.ideal_count["Ten"] + shoe.ideal_count["Jack"] + shoe.ideal_count["Queen"] + shoe.ideal_count["King"], 
                        self.dealer_possibilities["17"], self.dealer_possibilities["18"], self.dealer_possibilities["19"], self.dealer_possibilities["20"], 
                        self.dealer_possibilities["21"], self.dealer_possibilities["Busted"], winning_chance_hit, winning_chance_stand))
                            
                print("Win hit chance: " + str(winning_chance_hit))
                print("Win stand chance: " + str(winning_chance_stand))
                if winning_chance_hit > winning_chance_stand:
                    print("Hit")
                    
                    player_card = self.translate_card(input("Card from hit\n"))
                    self.hit_card(hand, shoe, Card(player_card, CARDS[player_card]))
                else :
                    print("Stand")
                    break

    def split_simulation(self, hand, shoe):
        new_hand = hand.split()
        self.hands.append(new_hand)
        # print "Splitted %s" % hand
        player_card = self.translate_card(input("Card from hit\n"))
        self.hit_card(new_hand, shoe, Card(player_card, CARDS[player_card]))
        player_card = self.translate_card(input("Card from hit\n"))
        self.hit_card(hand, shoe, Card(player_card, CARDS[player_card]))
        self.play_hand_simulation_percentage(new_hand, shoe)

    def play(self, shoe, dealer):
        for hand in self.hands:
            # print "Playing Hand: %s" % hand
            if STRATEGY=="CalculatePercentage":
                self.play_hand_percentage(hand, shoe, dealer)
            else:
                self.play_hand(hand, shoe)

    def play_hand_percentage(self, hand, shoe, dealer):
        if hand.length() < 2:
            if hand.cards[0].name == "Ace":
                hand.cards[0].value = 11
            self.hit(hand, shoe)

        while not hand.busted() and not hand.blackjack():
            self.splitted = False
            if hand.soft():
                flag = SOFT_STRATEGY[hand.value][self.dealer_hand.cards[0].name]
            elif hand.splitable():
                flag = PAIR_STRATEGY[hand.value][self.dealer_hand.cards[0].name]
            else:
                flag = HARD_STRATEGY[hand.value][self.dealer_hand.cards[0].name]

            if flag == 'D':
                if hand.length() == 2:
                    #print("Double Down")
                    hand.doubled = True
                    self.hit(hand, shoe)
                    break
                else:
                    flag = 'H'

            if flag == 'Sr':
                if hand.length() == 2:
                    #print("Surrender")
                    hand.surrender = True
                    break
                else:
                    flag = 'H'

            if flag == 'P':
                #print("Split")
                self.split(hand, shoe)
                self.splitted = True

            if not self.splitted:
                self.bust_chance, self.not_bust_chance = self.player_percentage_bust(hand, shoe)
                #print(self.bust_chance)
                if self.bust_chance == 0.0:
                    #print("AutoHit")
                    self.hit(hand, shoe)
                else:
                    rows = DATABASE.select_table("""SELECT * FROM BLACKJACK_CHANCES WHERE dealer=? AND Ace=? AND Two=? AND Three=? AND Four=? AND Five=? AND Six=?
                        AND Seven=? AND Eight=? AND Nine=? AND Ten=?""", 
                        (dealer.hand.cards[0].name, shoe.ideal_count["Ace"], shoe.ideal_count["Two"], shoe.ideal_count["Three"],
                        shoe.ideal_count["Four"], shoe.ideal_count["Five"], shoe.ideal_count["Six"], shoe.ideal_count["Seven"],
                        shoe.ideal_count["Eight"], shoe.ideal_count["Nine"], shoe.ideal_count["Ten"] + shoe.ideal_count["Jack"] + shoe.ideal_count["Queen"] + shoe.ideal_count["King"]))
                    winning_chance_hit = 0.0
                    winning_chance_stand = 0.0
                    if rows:
                        print("Chances already in database")
                        DATABASE.count_database_searchs += 1
                        winning_chance_hit = rows[0][18]
                        winning_chance_stand = rows[0][19]
                    else:
                        self.player_possibilities = {"17": 0.0, "18": 0.0, "19": 0.0, "20": 0.0, "21": 0.0, "Busted": 0.0}
                        self.dealer_possibilities = {"17": 0.0, "18": 0.0, "19": 0.0, "20": 0.0, "21": 0.0, "Busted": 0.0}
                        start = time.time()
                        self.calculate_percentage(dealer.hand, shoe, self.dealer_possibilities)
                        end = time.time()
                        #print("DEALER TIME ELAPSED ----------------------" + str(end - start) + "----------------------")
                        start = time.time()
                        self.calculate_percentage(hand, shoe, self.player_possibilities)
                        end = time.time()
                        #print("PLAYER TIME ELAPSED ----------------------" + str(end - start) + "----------------------")
                        #print(self.bust_chance)
                        #print("dealer_possibilities")
                        #print(self.dealer_possibilities)
                        #print(self.dealer_possibilities["17"] + self.dealer_possibilities["18"] + self.dealer_possibilities["19"] + self.dealer_possibilities["20"] + self.dealer_possibilities["21"] + self.dealer_possibilities["Busted"])
                        #print("player_possibilities")
                        #print(self.player_possibilities)
                        #print(self.player_possibilities["17"] + self.player_possibilities["18"] + self.player_possibilities["19"] + self.player_possibilities["20"] + self.player_possibilities["21"] + self.player_possibilities["Busted"])
                        winning_chance_hit, winning_chance_stand = self.winning_chance_calc(hand)
                        DATABASE.insert_update_table("""INSERT INTO BLACKJACK_CHANCES (
                            dealer, Ace, Two, Three, Four, Five, Six, Seven, Eight, Nine, Ten, Seventeen, Eightteen, Nineteen, Twenty, Twentyone, Busted, Winning_chance_hit, Winning_chance_stand) 
                            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", 
                            (dealer.hand.cards[0].name, shoe.ideal_count["Ace"], shoe.ideal_count["Two"], shoe.ideal_count["Three"],
                            shoe.ideal_count["Four"], shoe.ideal_count["Five"], shoe.ideal_count["Six"], shoe.ideal_count["Seven"],
                            shoe.ideal_count["Eight"], shoe.ideal_count["Nine"], shoe.ideal_count["Ten"] + shoe.ideal_count["Jack"] + shoe.ideal_count["Queen"] + shoe.ideal_count["King"], 
                            self.dealer_possibilities["17"], self.dealer_possibilities["18"], self.dealer_possibilities["19"], self.dealer_possibilities["20"], 
                            self.dealer_possibilities["21"], self.dealer_possibilities["Busted"], winning_chance_hit, winning_chance_stand))
                        #print("Chances inserted in database")

                        #print("winning_chance_hit:")
                        #print(winning_chance_hit)
                        #print("winning_chance_stand:")
                        #print(winning_chance_stand)
                    
                    if winning_chance_hit > winning_chance_stand:
                        #print("Hit")
                        self.hit(hand, shoe)
                    else :
                        #print("Stand")
                        break

    def winning_chance_calc(self, hand):
        winning_chance_hit = 0.0
        winning_chance_stand = 0.0
        #losing_chance_hit = 0.0
        #losing_chance_stand = 0.0
        
        if hand.value < 17:
            winning_chance_stand = self.dealer_possibilities["Busted"]
            #losing_chance_stand = self.dealer_possibilities["17"] + self.dealer_possibilities["18"] + self.dealer_possibilities["19"] + self.dealer_possibilities["20"] + self.dealer_possibilities["21"]
        elif hand.value == 17:
            #losing_chance_stand = (self.dealer_possibilities["17"]/2) + self.dealer_possibilities["18"] + self.dealer_possibilities["19"] + self.dealer_possibilities["20"] + self.dealer_possibilities["21"]
            winning_chance_stand = (self.dealer_possibilities["17"]/2) + self.dealer_possibilities["Busted"]
        elif hand.value == 18:
            #losing_chance_stand = (self.dealer_possibilities["18"]/2) + self.dealer_possibilities["19"] + self.dealer_possibilities["20"] + self.dealer_possibilities["21"]
            winning_chance_stand = (self.dealer_possibilities["18"]/2) + self.dealer_possibilities["17"] + self.dealer_possibilities["Busted"]
        elif hand.value == 19:
            #losing_chance_stand = (self.dealer_possibilities["19"]/2) + self.dealer_possibilities["20"] + self.dealer_possibilities["21"]
            winning_chance_stand = (self.dealer_possibilities["19"]/2) + self.dealer_possibilities["17"] + self.dealer_possibilities["18"] + self.dealer_possibilities["Busted"]
        elif hand.value == 20:
            #losing_chance_stand = (self.dealer_possibilities["20"]/2) + self.dealer_possibilities["21"]
            winning_chance_stand = (self.dealer_possibilities["20"]/2) + self.dealer_possibilities["17"] + self.dealer_possibilities["18"] + self.dealer_possibilities["19"] + self.dealer_possibilities["Busted"]
        elif hand.value == 21:            
            #losing_chance_stand = (self.dealer_possibilities["21"]/2)
            winning_chance_stand = (self.dealer_possibilities["21"]/2) + self.dealer_possibilities["17"] + self.dealer_possibilities["18"] + self.dealer_possibilities["19"] + self.dealer_possibilities["20"] + self.dealer_possibilities["Busted"]

        winning_chance_hit += self.player_possibilities["17"] * (self.dealer_possibilities["17"]/2 + self.dealer_possibilities["Busted"])
        winning_chance_hit += self.player_possibilities["18"] * (self.dealer_possibilities["18"]/2 + self.dealer_possibilities["17"] + self.dealer_possibilities["Busted"])
        winning_chance_hit += self.player_possibilities["19"] * (self.dealer_possibilities["19"]/2 + self.dealer_possibilities["18"] + self.dealer_possibilities["17"] + self.dealer_possibilities["Busted"])
        winning_chance_hit += self.player_possibilities["20"] * (self.dealer_possibilities["20"]/2 + self.dealer_possibilities["19"] + self.dealer_possibilities["18"] + self.dealer_possibilities["17"] + self.dealer_possibilities["Busted"])
        winning_chance_hit += self.player_possibilities["21"] * (self.dealer_possibilities["21"]/2 + self.dealer_possibilities["20"] + self.dealer_possibilities["19"] + self.dealer_possibilities["18"] + self.dealer_possibilities["17"] + self.dealer_possibilities["Busted"])

        #losing_chance_hit += self.player_possibilities["Busted"]
        #losing_chance_hit += self.player_possibilities["21"] * (self.dealer_possibilities["21"]/2)
        #losing_chance_hit += self.player_possibilities["20"] * (self.dealer_possibilities["20"]/2 + self.dealer_possibilities["21"])
        #losing_chance_hit += self.player_possibilities["19"] * (self.dealer_possibilities["19"]/2 + self.dealer_possibilities["20"] + self.dealer_possibilities["21"])
        #losing_chance_hit += self.player_possibilities["18"] * (self.dealer_possibilities["18"]/2 + self.dealer_possibilities["19"] + self.dealer_possibilities["20"] + self.dealer_possibilities["21"])
        #losing_chance_hit += self.player_possibilities["17"] * (self.dealer_possibilities["17"]/2 + self.dealer_possibilities["18"] + self.dealer_possibilities["19"] + self.dealer_possibilities["20"] + self.dealer_possibilities["21"])

        #print("losing_chance_stand")
        #print(losing_chance_stand)
        #print("losing_chance_hit")
        #print(losing_chance_hit)

        return winning_chance_hit, winning_chance_stand

    def player_percentage_bust(self, hand, shoe):
        not_bust_chance = 0.0
        bust_chance = 0.0
        for card in CARDS:
            if shoe.ideal_count[card]>0:
                copy_shoe = copy.deepcopy(shoe)
                copy_hand = copy.deepcopy(hand)
                self.hit_card(copy_hand, copy_shoe, Card(card, CARDS[card]))
                if copy_hand.value > 21:
                    bust_chance += shoe.ideal_count[card]/shoe.total_card()
                else :
                    not_bust_chance += shoe.ideal_count[card]/shoe.total_card()

        #print("Not Bust Chance = " + str(not_bust_chance))
        #print("Bust Chance = " + str(bust_chance))
        return bust_chance, not_bust_chance

    def calculate_percentage(self, hand, shoe, possibilities, possibility=1):
        #print("Possibilities")
        #print(possibilities)
        for card in CARDS:
            if shoe.ideal_count[card]>0:
                copy_shoe = copy.deepcopy(shoe)
                copy_hand = copy.deepcopy(hand)
                new_possibility = possibility * copy_shoe.ideal_count[card]/copy_shoe.total_card()
                self.hit_card(copy_hand, copy_shoe, Card(card, CARDS[card]))
                
                if copy_hand.value == 17:
                    possibilities["17"] += new_possibility
                elif copy_hand.value == 18:
                    possibilities["18"] += new_possibility
                elif copy_hand.value == 19:
                    possibilities["19"] += new_possibility
                elif copy_hand.value == 20:
                    possibilities["20"] += new_possibility
                elif copy_hand.value == 21:
                    possibilities["21"] += new_possibility
                elif copy_hand.value > 21:
                    possibilities["Busted"] += new_possibility
                    start = False
                    for y in CARDS:
                        if start:
                            others_possibility = possibility * copy_shoe.ideal_count[y]/copy_shoe.total_card()
                            possibilities["Busted"] += others_possibility
                        if y == card:
                            start = True
                    break
                else:
                    self.calculate_percentage(copy_hand, copy_shoe, possibilities, new_possibility)

    def play_hand(self, hand, shoe):
        if hand.length() < 2:
            if hand.cards[0].name == "Ace":
                hand.cards[0].value = 11
            self.hit(hand, shoe)

        while not hand.busted() and not hand.blackjack():
            if hand.soft():
                flag = SOFT_STRATEGY[hand.value][self.dealer_hand.cards[0].name]
            elif hand.splitable():
                flag = PAIR_STRATEGY[hand.value][self.dealer_hand.cards[0].name]
            else:
                flag = HARD_STRATEGY[hand.value][self.dealer_hand.cards[0].name]

            if flag == 'D':
                if hand.length() == 2:
                    # print "Double Down"
                    hand.doubled = True
                    self.hit(hand, shoe)
                    break
                else:
                    flag = 'H'

            if flag == 'Sr':
                if hand.length() == 2:
                    # print "Surrender"
                    hand.surrender = True
                    break
                else:
                    flag = 'H'

            if flag == 'H':
                self.hit(hand, shoe)

            if flag == 'P':
                self.split(hand, shoe)

            if flag == 'S':
                break

    def hit_card(self, hand, shoe, card):
        c = shoe.deal_card(card)
        hand.add_card(c)
        # print "Hitted: %s" % c

    def hit(self, hand, shoe):
        c = shoe.deal()
        hand.add_card(c)
        # print "Hitted: %s" % c

    def split(self, hand, shoe):
        self.hands.append(hand.split())
        # print "Splitted %s" % hand
        self.play_hand(hand, shoe)


class Dealer(object):
    """
    Represent the dealer
    """
    def __init__(self, hand=None):
        self.hand = hand

    def set_hand(self, new_hand):
        self.hand = new_hand

    def play(self, shoe):
        while self.hand.value < 17:
            self.hit(shoe)

    def hit(self, shoe):
        c = shoe.deal()
        self.hand.add_card(c)
        # print "Dealer hitted: %s" %c

    # Returns an array of 6 numbers representing the probability that the final score of the dealer is
    # [17, 18, 19, 20, 21, Busted] '''
    # TODO Differentiate 21 and BJ
    # TODO make an actual tree, this is false AF
    def get_probabilities(self) :
        start_value = self.hand.value
        # We'll draw 5 cards no matter what an count how often we got 17, 18, 19, 20, 21, Busted

class Tree(object):
    """
    A tree that opens with a statistical card and changes as a new
    statistical card is added. In this context, a statistical card is a list of possible values, each with a probability.
    e.g : [2 : 0.05, 3 : 0.1, ..., 22 : 0.1]
    Any value above 21 will be truncated to 22, which means 'Busted'.
    """
    #TODO to test
    def __init__(self, start=[]):
        self.tree = []
        self.tree.append(start)

    def add_a_statistical_card(self, stat_card):
        # New set of leaves in the tree
        leaves = []
        for p in self.tree[-1] :
            for v in stat_card :
                new_value = v + p
                proba = self.tree[-1][p]*stat_card[v]
                if (new_value > 21) :
                    # All busted values are 22
                    new_value = 22
                if (new_value in leaves) :
                    leaves[new_value] = leaves[new_value] + proba
                else :
                    leaves[new_value] = proba


class Game(object):
    """
    A sequence of Blackjack Rounds that keeps track of total money won or lost
    """
    def __init__(self):
        self.shoe = Shoe(SHOE_SIZE)
        self.money = 0.0
        self.bet = 0.0
        self.stake = 1.0
        self.player = Player()
        self.dealer = Dealer()
        self.count_higher_bet = 0

    def get_hand_winnings(self, hand):
        win = 0.0
        bet = self.stake
        if not hand.surrender:
            if hand.busted():
                status = "LOST"
            else:
                if hand.blackjack():
                    if self.dealer.hand.blackjack():
                        status = "PUSH"
                    else:
                        status = "WON 3:2"
                elif self.dealer.hand.busted():
                    status = "WON"
                elif self.dealer.hand.value < hand.value:
                    status = "WON"
                elif self.dealer.hand.value > hand.value:
                    status = "LOST"
                elif self.dealer.hand.value == hand.value:
                    if self.dealer.hand.blackjack():
                        status = "LOST"  # player's 21 vs dealers blackjack
                    else:
                        status = "PUSH"
        else:
            status = "SURRENDER"

        if status == "LOST":
            win += -1
        elif status == "WON":
            win += 1
        elif status == "WON 3:2":
            win += 1.5
        elif status == "SURRENDER":
            win += -0.5
        if hand.doubled:
            win *= 2
            bet *= 2

        win *= self.stake

        return win, bet

    def play_round_simulation(self):
        if self.shoe.truecount() == 3:
            self.stake = BET_SPREAD_3
            self.count_higher_bet+=1
        elif self.shoe.truecount() == 4:
            self.stake = BET_SPREAD_4
            self.count_higher_bet+=1
        elif self.shoe.truecount() == 5:
            self.stake = BET_SPREAD_5
            self.count_higher_bet+=1
        elif self.shoe.truecount() == 6:
            self.stake = BET_SPREAD_6
            self.count_higher_bet+=1
        elif self.shoe.truecount() > 6:
            self.stake = BET_SPREAD
            self.count_higher_bet+=1
        else:
            self.stake = 1.0

        print("Bet:" + str(self.stake))

        print("End round = e | Play round = p | Ace = 1 | Jack = j | Queen = q | King = k | 2, 3, 4, 5, 6, 7, 8, 9")
        dealer_card = input("Input Dealer's card:")
        dealer_card = self.translate_card(dealer_card)
        dealer_hand = Hand([self.shoe.deal_card(Card(dealer_card, CARDS[dealer_card]))])
        self.dealer.set_hand(dealer_hand)
        print(self.dealer.hand)

        print("Input Player's card")
        player_card1 = self.translate_card(input())
        player_card2 = self.translate_card(input())
        player_hand = Hand([self.shoe.deal_card(Card(player_card1, CARDS[player_card1])), self.shoe.deal_card(Card(player_card2, CARDS[player_card2]))])
        self.player.set_hands(player_hand, dealer_hand)
        #print(self.player.hands)

        self.blackjackSecurity = False
        if self.dealer.hand.cards[0].name == "Ace":
            #print("----------------------")
            #print("Dealer hand:")
            #print(dealer_hand.__str__())
            winning_chances = self.check_insurance()
            print("Insurance winning chances:")
            print(winning_chances)
            if winning_chances >= 0.5:
                self.blackjackSecurity = True
                print("---------------")
                print("CALL INSURANCE")
                print("---------------")

        print("Input other's card")
        while True:
            other_card = input()
            if other_card == "e":
                break
            elif other_card == "p":
                self.player.play_simulation(self.shoe, self.dealer)
                print("Input Dealer's draw card:")
                while self.dealer.hand.value < 17:
                    dealer_card = self.translate_card(input())
                    self.dealer.hand.add_card(self.shoe.deal_card(Card(dealer_card, CARDS[dealer_card])))
            else:
                other_card = self.translate_card(other_card)
                self.shoe.deal_card(Card(other_card, CARDS[other_card]))

                
        for hand in self.player.hands:
            win, bet = self.get_hand_winnings(hand)
            self.money += win
            self.bet += bet

    def translate_card(self, card):
        if card == "1":
            card = "Ace"
        elif card == "2":
            card = "Two"
        elif card == "3":
            card = "Three"
        elif card == "4":
            card = "Four"
        elif card == "5":
            card = "Five"
        elif card == "6":
            card = "Six"
        elif card == "7":
            card = "Seven"
        elif card == "8":
            card = "Eight"
        elif card == "9":
            card = "Nine"
        elif card == "10":
            card = "Ten"
        elif card == "j":
            card = "Jack"
        elif card == "q":
            card = "Queen"
        elif card == "k":
            card = "King"
        return card

    def play_round(self):
        if self.shoe.truecount() == 3:
            self.stake = BET_SPREAD_3
            self.count_higher_bet+=1
        elif self.shoe.truecount() == 4:
            self.stake = BET_SPREAD_4
            self.count_higher_bet+=1
        elif self.shoe.truecount() == 5:
            self.stake = BET_SPREAD_5
            self.count_higher_bet+=1
        elif self.shoe.truecount() == 6:
            self.stake = BET_SPREAD_6
            self.count_higher_bet+=1
        elif self.shoe.truecount() > 6:
            self.stake = BET_SPREAD
            self.count_higher_bet+=1
        else:
            self.stake = 1.0

        player_hand = Hand([self.shoe.deal(), self.shoe.deal()])
        dealer_hand = Hand([self.shoe.deal()])
        self.player.set_hands(player_hand, dealer_hand)
        self.dealer.set_hand(dealer_hand)
        # print "Dealer Hand: %s" % self.dealer.hand
        # print "Player Hand: %s\n" % self.player.hands[0]

        # To do Insurance
        self.blackjackSecurity = False
        if self.dealer.hand.cards[0].name == "Ace":
            #print("----------------------")
            #print("Dealer hand:")
            #print(dealer_hand.__str__())
            winning_chances = self.check_insurance()
            #print("winning_chances")
            #print(winning_chances)
            if winning_chances >= 0.5:
                self.blackjackSecurity = True
                print("---------------")
                print("CALL INSURANCE")
                print("---------------")

        
        self.player.play(self.shoe, self.dealer)
        self.dealer.play(self.shoe)

        for hand in self.player.hands:
            win, bet = self.get_hand_winnings(hand)
            self.money += win
            self.bet += bet
            # print "Player Hand: %s %s (Value: %d, Busted: %r, BlackJack: %r, Splithand: %r, Soft: %r, Surrender: %r, Doubled: %r)" % (hand, status, hand.value, hand.busted(), hand.blackjack(), hand.splithand, hand.soft(), hand.surrender, hand.doubled)

        # print "Dealer Hand: %s (%d)" % (self.dealer.hand, self.dealer.hand.value)

    def check_insurance(self):
        winnable = 0
        total = 0
        for card in CARDS:
            #print(card)
            #print(type(card))
            if card=="Ten" or card=="Jack" or card=="Queen" or card=="King":
                winnable += self.shoe.ideal_count[card]

            total += self.shoe.ideal_count[card]

        return winnable/total

    def get_money(self):
        return self.money

    def get_count_higher_bet(self):
        return self.count_higher_bet

    def get_bet(self):
        return self.bet

if __name__ == "__main__":
    importer = StrategyImporter(sys.argv[1])
    STRATEGY=sys.argv[2]
    simulation=sys.argv[3]
    HARD_STRATEGY, SOFT_STRATEGY, PAIR_STRATEGY = importer.import_player_strategy()
    DATABASE = Database("./database/bj_simulation_database.sqlite")
    
    moneys = []
    bets = []
    countings = []
    nb_hands = 0
    accumulate_win=0.0
    max_drawdown=0.0
    max_win=0.0
    count_higher_bet=0
    for g in range(GAMES):
        game = Game()

        if simulation == "simulation":
            while not game.shoe.reshuffle:
                # print '%s GAME no. %d %s' % (20 * '#', i + 1, 20 * '#')
                game.play_round_simulation()
                nb_hands += 1
        else:
            while not game.shoe.reshuffle:
                # print '%s GAME no. %d %s' % (20 * '#', i + 1, 20 * '#')
                game.play_round()
                nb_hands += 1

        moneys.append(game.get_money())
        bets.append(game.get_bet())
        countings += game.shoe.count_history
        accumulate_win+=game.get_money()
        count_higher_bet+=game.get_count_higher_bet()
        if max_drawdown>accumulate_win:
            max_drawdown = accumulate_win
        elif max_win<accumulate_win:
            max_win=accumulate_win

        print("WIN for Game no. %d: %s (%s bet) (%s accumulate win) (%s times higher bets) (%s find chances in database)" % (g + 1, "{0:.2f}".format(game.get_money()), "{0:.2f}".format(game.get_bet()), accumulate_win, count_higher_bet, str(DATABASE.count_database_searchs)))

    sume = 0.0
    total_bet = 0.0
    for value in moneys:
        sume += value
    for value in bets:
        total_bet += value

    print("\n%d hands overall, %0.2f hands per game on average" % (nb_hands, float(nb_hands) / GAMES))
    print("%0.2f total bet" % total_bet)
    print("Overall winnings: {} (edge = {} %)".format("{0:.2f}".format(sume), "{0:.3f}".format(100.0*sume/total_bet)))
    print("%0.2f max drawdown" % max_drawdown)
    print("%0.2f max win" % max_win)

    moneys = sorted(moneys)
    fit = stats.norm.pdf(moneys, np.mean(moneys), np.std(moneys))  # this is a fitting indeed
    pl.plot(moneys, fit, '-o')
    pl.hist(moneys)
    #pl.show()

    plt.ylabel('count')
    plt.plot(countings, label='x')
    plt.legend()
    #plt.show()
