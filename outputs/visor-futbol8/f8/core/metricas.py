"""The eleven player metrics and the action kinds that feed them. Single source for every module."""
METRICS={
 'goals':'Goles','assists':'Asistencias','big_chances':'Grandes chances creadas',
 'balls_into_box':'Balones al área','fouls_won':'Faltas provocadas','fouls_committed':'Faltas cometidas',
 'recoveries':'Robos de balón','successful_dribbles':'Regates efectivos','shots':'Tiros totales',
 'passes':'Pases','turnovers':'Balones perdidos'}
METRIC_KEYS=tuple(METRICS)
METRIC_MAP={'goal':['goals','shots'],'shot':['shots'],'assist':['assists'],'big_chance':['big_chances'],'ball_into_box':['balls_into_box'],'foul_won':['fouls_won'],'foul_committed':['fouls_committed'],'recovery':['recoveries'],'dribble':['successful_dribbles'],'pass':['passes'],'turnover':['turnovers']}
