#!/bin/python3
import discord
from discord.ext import commands, tasks
import database
import chess
import chess.svg
import asyncio
import pickle
import cairosvg
from time import time
from discord.ext import commands
from discord_components import *


class Game:
    def __init__(self, white, black, guild):
        self.board = chess.Board()
        self.moves = 0
        self.player = white
        self.players = (white, black)
        self.last_move = None
        database.update_chessdata(white, guild, None, black)
        database.update_chessdata(black, guild, None, white)
        
    def make_move(self, move):
        """
        Returns        
        -1      invalid san move
        -2      illegal move
        -3      ambiguous move
        result  game ended
        """
        try:
            self.last_move = self.board.push_san(move)
        except ValueError as e:
            if str(e)[:4] == 'ille':
                return -2
            elif str(e)[:4] == 'inva':
                return -1
            elif str(e)[:4] == 'ambi':
                return -3
        self.moves += 1
        if self.board.is_game_over():
            return self.board.result()
        self.player = self.players[self.moves % 2]

    def board_to_svg(self):
        if self.board.is_check():
            bk = self.board.king(chess.BLACK)
            wk = self.board.king(chess.WHITE)
            if self.board.is_attacked_by(chess.WHITE, bk):
                check = bk
            else:
                check = wk
        else:
            check = None
        return chess.svg.board(self.board, size=350, check=check, lastmove=self.last_move, orientation=(self.player==self.players[0]))


class Chess(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.game_cleanup.start()
        DiscordComponents(bot)
        
    def ban_check(self, author, member):
        ban_data = database.is_botban(author.id)
        if ban_data is not None:
            embed = discord.Embed(title='Bot ban',
                                  description=f"{author.mention} you are banned from using {self.bot.user.mention} till <t:{ban_data[1]}:F>",
                                  color=0xF2A2C0)
            return embed
        elif database.is_botban(member.id) is not None:
            embed = discord.Embed(title='Bot ban',
                                  description=f"{member.mention} is banned from using {self.bot.user.mention}.",
                                  color=0xF2A2C0)
            return embed

    @tasks.loop(seconds=60 * 5)
    async def game_cleanup(self):
        database.clear_chess_game()

    @commands.command()
    @commands.guild_only()
    async def chess(self, ctx, member:discord.Member):
        if ctx.author.bot:
            return
        
        elif member.bot:  # when mentioned member is bot
            embed = discord.Embed(description=f"{member.mention} is a bot not a Person!",
                                  color=0xF2A2C0)
            await ctx.send(embed=embed)
            return
        
        elif member == ctx.author:
            embed = discord.Embed(description=f"{member.mention} find a friend to play with and don't be so lonely",
                                  color=0xF2A2C0)
            await ctx.send(embed=embed)
            return
            
        ban_embed = self.ban_check(ctx.author, member)
        if ban_embed is not None:
            await ctx.send(embed=ban_embed)
            return
        
        author_chessdata = database.get_chessdata(ctx.author.id, ctx.guild.id)
        member_chessdata = database.get_chessdata(member.id, ctx.guild.id)
        if author_chessdata[6] != 0:
            embed = discord.Embed(description=f"{ctx.author.mention} you are already in a game with <@{author_chessdata[6]}>",
                                  color=0xF2A2C0)
            await ctx.send(embed=embed)
            return
        elif member_chessdata[6] != 0:
            embed = discord.Embed(description=f"{member.mention} is already in a game with <@{member_chessdata[6]}>",
                                  color=0xF2A2C0)
            await ctx.send(embed=embed)
            return
        embed = discord.Embed(description=f"{ctx.author.mention} wants to play chess with you {member.mention}",
                              color=0xF2A2C0)
        m = await ctx.send(embed=embed, components=[[Button(style=ButtonStyle.green, label="Accept"),
                                                     Button(style=ButtonStyle.red, label='Reject')]])
        def check(res):
            return member == res.user and res.message.id == m.id
            
        try:
            response = await self.bot.wait_for('button_click', timeout=30, check=check)
            await response.respond(type=6)
            if response.component.label == 'Accept':
                await m.delete()
                game = Game(ctx.author.id, member.id, ctx.guild.id)
                board_embed = discord.Embed(title=f"{ctx.author.nick or ctx.author.name} vs {member.nick or member.name}")
                board_embed.set_image(url='https://cdn.discordapp.com/attachments/896487377038610472/912223704359002132/board.png')
                board_embed.set_author(name=f"{ctx.author.nick or ctx.author.name}'s turn", icon_url=ctx.author.avatar_url)
                board_embed.add_field(name="Commands", value="**`t.move e4`** to make a move, *use Algebraic notation* \n**`t.resign`** to resign the game", inline=False)
                board_embed.set_footer(text='this game will be aborted if it takes longer than 3h I don\'t care about game outcome')
                await ctx.send(f"{ctx.author.mention} your turn", embed=board_embed)
                game_byte = pickle.dumps(game)
                database.dump_chess_game(game.player, ctx.guild.id, game_byte, int(str(time() + 3 * 60 *60)[:10]))

            elif response.component.label == 'Reject':
                embed = discord.Embed(description=f"{member.mention} Rejected the challenge from {ctx.author.mention}",
                                      color=0xF2A2C0)
            await m.edit(embed=embed, components=[])
        except asyncio.TimeoutError:
            embed = discord.Embed(description=f"{member.mention} failed to respond in time *30 seconds*",
                                  color=0xF2A2C0)
            await m.edit(embed=embed, components=[])
            
    @commands.command(aliases=['m'])
    @commands.guild_only()
    async def move(self, ctx, move):
        data = database.load_chess_game(ctx.author.id, ctx.guild.id)
        if data is None:
            embed = discord.Embed(description=f"{ctx.author.mention}, you are not in a game or it's not your turn to make a move",
                                  color=0xF2A2C0)
            await ctx.reply(embed=embed)
        else:
            game = pickle.loads(data[2])
            game_response = game.make_move(move)

            if game_response == -1:
                embed = discord.Embed(description=f"`{move}` is an invalid move use Algebraic notation to make your move",
                                      color=0xF2A2C0)
                await ctx.reply(embed=embed)
                
            elif game_response == -2:
                embed = discord.Embed(description=f"`{move}` is an illegal move",
                                      color=0xF2A2C0)
                await ctx.reply(embed=embed)
                
            elif game_response == -3:
                embed = discord.Embed(description=f"`{move}` is an ambiguous move",
                                      color=0xF2A2C0)
                await ctx.reply(embed=embed)
                
            elif game_response == '1-0':
                winner = ctx.guild.get_member(game.player)
                losser = ctx.guild.get_member(game.players[game.moves % 2])
                svg = game.board_to_svg()
                with open(f"{ctx.author.id}.svg", 'w') as f:
                    f.write(svg)
                    cairosvg.svg2png(url=f"{ctx.author.id}.svg", write_to=f"{ctx.author.id}.png")
                    fi = discord.File(f"{ctx.author.id}.png", filename=f"{ctx.author.id}.png")
                    embed = discord.Embed(title=f"{winner.nick or winner.name} vs {losser.nick or losser.name}",
                                          color=0x2C42BF)
                    embed.set_thumbnail(url=winner.avatar_url)
                    embed.set_author(name=f"{winner.nick or winner.name} won the match", icon_url=winner.avatar_url)
                    embed.set_image(url=f"attachment://{ctx.author.id}.png")
                    await ctx.send(embed=embed, file =fi)           
                    
                database.update_chessdata(winner.id, ctx.guild.id, 1, None)
                database.update_chessdata(losser.id, ctx.guild.id, -1, None)
                database.delete_chess_game(ctx.author.id, ctx.guild.id)
                
                if ctx.channel.is_nsfw():
                    if set(database.get_config('domme', ctx.guild.id)) & set([role.id for role in winner.roles]) and set(database.get_config('slave', ctx.guild.id)) & set([role.id for role in losser.roles]):
                        embed = discord.Embed(title='Queen always wins',
                                              color=0x2C42BF)
                        embed.set_author(name=f"{winner.nick or winner.name}", icon_url=winner.avatar_url)
                        embed.set_image(url='https://cdn.discordapp.com/attachments/912235660788768778/912485772983169024/tumblr_muq2oyoz7Y1rrcosjo1_500.png')
                        await ctx.send(f"{losser.mention}", embed=embed)
            
            elif game_response == '0-1':
                losser = ctx.guild.get_member(game.players[game.moves % 2])
                winner = ctx.guild.get_member(game.player)
                svg = game.board_to_svg()
                with open(f"{ctx.author.id}.svg", 'w') as f:
                    f.write(svg)
                    cairosvg.svg2png(url=f"{ctx.author.id}.svg", write_to=f"{ctx.author.id}.png")
                    fi = discord.File(f"{ctx.author.id}.png", filename=f"{ctx.author.id}.png")
                    embed = discord.Embed(title=f"{winner.nick or winner.name} vs {losser.nick or losser.name}",
                                          color=0x2C42BF)
                    embed.set_thumbnail(url=winner.avatar_url)
                    embed.set_author(name=f"{winner.nick or winner.name} won the match", icon_url=winner.avatar_url)
                    embed.set_image(url=f"attachment://{ctx.author.id}.png")
                    await ctx.send(embed=embed, file =fi)           
                    
                database.update_chessdata(winner.id, ctx.guild.id, 1, None)
                database.update_chessdata(losser.id, ctx.guild.id, -1, None)
                database.delete_chess_game(ctx.author.id, ctx.guild.id)
                
                if ctx.channel.is_nsfw():
                    if set(database.get_config('domme', ctx.guild.id)) & set([role.id for role in winner.roles]) and set(database.get_config('slave', ctx.guild.id)) & set([role.id for role in losser.roles]):
                        embed = discord.Embed(title='Queen always wins',
                                              color=0x2C42BF)
                        embed.set_author(name=f"{winner.nick or winner.name}", icon_url=winner.avatar_url)
                        embed.set_image(url='https://cdn.discordapp.com/attachments/912235660788768778/912485772983169024/tumblr_muq2oyoz7Y1rrcosjo1_500.png')
                        await ctx.send(f"{losser.mention}", embed=embed)

            elif game_response == '1/2-1/2':
                svg = game.board_to_svg()
                with open(f"{ctx.author.id}.svg", 'w') as f:
                    f.write(svg)
                    cairosvg.svg2png(url=f"{ctx.author.id}.svg", write_to=f"{ctx.author.id}.png")
                    fi = discord.File(f"{ctx.author.id}.png", filename=f"{ctx.author.id}.png")
                    embed = discord.Embed(description=f"anticlimactic ending between <@{game.players[0]}> and <@{game.player[1]}>",
                                          color=0x808080)
                    embed.set_image(url=f"attachment://{ctx.author.id}.png")
                    await ctx.send(embed=embed, file =fi)           
                    
                database.update_chessdata(game.players[0], ctx.guild.id, 0, None)
                database.update_chessdata(game.players[1], ctx.guild.id, 0, None)
                database.delete_chess_game(ctx.author.id, ctx.guild.id)
                
            elif game_response == None:
                svg = game.board_to_svg()
                with open(f"{ctx.author.id}.svg", 'w') as f:
                    f.write(svg)
                    cairosvg.svg2png(url=f"{ctx.author.id}.svg", write_to=f"{ctx.author.id}.png")
                    fi = discord.File(f"{ctx.author.id}.png", filename=f"{ctx.author.id}.png")
                    opp_player = ctx.guild.get_member(game.player)
                    board_embed = discord.Embed(title=f"{ctx.author.nick or ctx.author.name} vs {opp_player.nick or opp_player.name}",
                                                color=0xFF2030 if game.board.is_check() else 0xF2A2C0)
                    board_embed.set_image(url=f"attachment://{ctx.author.id}.png")
                    board_embed.set_author(name=f"{opp_player.nick or opp_player.name}'s turn", icon_url=opp_player.avatar_url)
                    board_embed.add_field(name="Commands", value="**`t.move e4`** to make a move, *use Algebraic notation* \n**`t.resign`** to resign the game", inline=False)
                    board_embed.set_footer(text='this game will be aborted if it takes longer than 3h I don\'t care about game outcome')
                    await ctx.send(f"{opp_player.mention} your turn", embed=board_embed, file =fi)
                game_byte = pickle.dumps(game)
                database.update_chess_game(ctx.author.id, ctx.guild.id, game_byte, opp_player.id)                 


    @commands.command()
    @commands.guild_only()
    async def resign(self, ctx):
        if ctx.author.bot:
            return
        
        playing_with = database.get_chessdata(ctx.author.id, ctx.guild.id)[6]
        if playing_with == 0:
            embed = discord.Embed(description=f"{ctx.author.mention} you are not in a game to resign",
                                  color=0xF2A2C0)
            await ctx.reply(embed=embed)
        else:
            game = pickle.loads(database.load_chess_game(ctx.author.id, ctx.guild.id)[2] or database.load_chess_game(playing_with, ctx.guild.ctx)[2])
            winner = ctx.guild.get_member(playing_with)
            losser = ctx.author
            svg = game.board_to_svg()
            with open(f"{ctx.author.id}.svg", 'w') as f:
                f.write(svg)
                cairosvg.svg2png(url=f"{ctx.author.id}.svg", write_to=f"{ctx.author.id}.png")
                fi = discord.File(f"{ctx.author.id}.png", filename=f"{ctx.author.id}.png")
                embed = discord.Embed(title=f"{winner.nick or winner.name} vs {losser.nick or losser.name}",
                                        color=0x2C42BF)
                embed.set_thumbnail(url=winner.avatar_url)
                embed.set_author(name=f"{winner.nick or winner.name} won the match by resignation", icon_url=winner.avatar_url)
                embed.set_image(url=f"attachment://{ctx.author.id}.png")
                await ctx.send(embed=embed, file =fi)           
                    
            database.update_chessdata(winner.id, ctx.guild.id, 1, None)
            database.update_chessdata(losser.id, ctx.guild.id, -1, None)
            database.delete_chess_game(ctx.author.id, ctx.guild.id)
            database.delete_chess_game(playing_with, ctx.guild.id)

    @chess.error
    async def on_chess_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument) or isinstance(error, commands.BadArgument) or isinstance(error, commands.MemberNotFound):
            embed = discord.Embed(description=f"Usage:\n**`t.chess @mention`**",
                                  color=0xFF2030)
            await ctx.send(embed=embed)

def setup(bot):
    bot.add_cog(Chess(bot))
