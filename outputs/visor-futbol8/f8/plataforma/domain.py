"""Interval-scoped identities and reviewed football event accounting."""
import math

from f8.core.metricas import METRICS
EVENTS={'shot':'Tiro','assist':'Asistencia','big_chance':'Gran chance creada','ball_into_box':'Balón al área',
 'foul_won':'Falta provocada','foul_committed':'Falta cometida','recovery':'Robo de balón',
 'dribble':'Regate','pass':'Pase','turnover':'Balón perdido'}
DEFINITIONS={
 'goals':'Tiro que termina en gol del equipo y se atribuye al jugador. Los autogoles no se atribuyen como goles de un atacante.',
 'assists':'Última intervención intencional que habilita directamente al autor de un gol confirmado. Registrar una vez por gol; revisar rebotes y desvíos.',
 'big_chances':'Acción que deja a un compañero una ocasión clara: mano a mano o remate cercano con oposición limitada. Juicio del analista, no una métrica certificada de un proveedor.',
 'balls_into_box':'Pase o centro cuya trayectoria entra en el área rival. Puede contar aunque no llegue a un compañero; excluye conducciones.',
 'fouls_won':'Infracción del rival sufrida por el jugador y señalada por el árbitro o confirmada claramente en la revisión.',
 'fouls_committed':'Infracción cometida por el jugador y señalada por el árbitro o confirmada claramente en la revisión.',
 'recoveries':'Recuperación del control del balón frente a una posesión rival. Una simple disputa o toque no basta.',
 'successful_dribbles':'El jugador supera a un rival con el balón y conserva el control. Un cambio de dirección sin superar a un rival no cuenta.',
 'shots':'Intento deliberado de marcar: incluye goles, paradas, bloqueos y tiros fuera. No incluye centros sin intención de remate.',
 'passes':'Intentos intencionales de entregar el balón a un compañero. Se conserva si fue completado, fallido o incierto; el total mostrado son intentos.',
 'turnovers':'Acción que termina la posesión del equipo por un error o desposesión. No se deriva automáticamente de todo pase incompleto; los tiros no se consideran pérdida.'}

def number(value,name):
    if isinstance(value,bool):raise ValueError(f'{name}: número inválido')
    try:x=float(value)
    except (ValueError,TypeError):raise ValueError(f'{name}: número inválido')
    if not math.isfinite(x):raise ValueError(f'{name}: debe ser finito')
    return x

def validate_event(value,players,duration):
    if not isinstance(value,dict):raise ValueError('Acción inválida')
    player=value.get('player_id');kind=value.get('kind');state=value.get('status','pending')
    if player not in players:raise ValueError('Jugador desconocido')
    if kind not in EVENTS:raise ValueError('Tipo de acción desconocido')
    if state not in ('pending','confirmed'):raise ValueError('Estado desconocido')
    t=number(value.get('time'),'Tiempo')
    if not 0<=t<=duration:raise ValueError('Tiempo fuera del vídeo')
    outcome=str(value.get('outcome','unknown'))
    allowed={'shot':{'goal','saved','off_target','blocked','unknown'},'pass':{'complete','incomplete','unknown'},'dribble':{'success','failed','unknown'}}
    if outcome not in allowed.get(kind,{'unknown'}):raise ValueError('Resultado incompatible con la acción')
    flags={k:value.get(k,False) for k in ('ball_into_box','big_chance','turnover')}
    if any(not isinstance(v,bool) for v in flags.values()):raise ValueError('Las etiquetas deben ser booleanas')
    if kind!='pass' and (flags['ball_into_box'] or flags['big_chance']):raise ValueError('Área y chance como etiquetas requieren un pase')
    if flags['turnover'] and kind not in ('pass','dribble'):raise ValueError('Pérdida como etiqueta requiere pase o regate')
    if kind=='shot' and outcome=='goal' and state=='confirmed':pass
    note=value.get('note','')
    if not isinstance(note,str) or len(note)>2000:raise ValueError('Nota demasiado larga o inválida')
    related=value.get('goal_event_id')
    if related is not None:
        if kind!='assist':raise ValueError('Solo una asistencia se vincula a un gol')
        if isinstance(related,bool) or not isinstance(related,int) or related<1:raise ValueError('Gol vinculado inválido')
    return {'player_id':player,'kind':kind,'time':round(t,4),'status':state,'outcome':outcome,**flags,'note':note,'goal_event_id':related}

def contributions(event):
    result=dict.fromkeys(METRICS,0)
    if event['status']!='confirmed':return result
    kind=event['kind']
    mapping={'assist':'assists','big_chance':'big_chances','ball_into_box':'balls_into_box','foul_won':'fouls_won','foul_committed':'fouls_committed','recovery':'recoveries','pass':'passes','turnover':'turnovers'}
    if kind in mapping:result[mapping[kind]]+=1
    if kind=='shot':
        result['shots']+=1
        if event['outcome']=='goal':result['goals']+=1
    if kind=='dribble' and event['outcome']=='success':result['successful_dribbles']+=1
    if kind=='pass':
        if event['ball_into_box']:result['balls_into_box']+=1
        if event['big_chance']:result['big_chances']+=1
    if kind in ('pass','dribble') and event['turnover']:result['turnovers']+=1
    return result

def aggregate(events,players):
    result={pid:{'player_id':pid,'metrics':dict.fromkeys(METRICS,0),'confirmed_events':0,'pending_events':0,'passes_completed':0,'passes_incomplete':0,'passes_unknown':0} for pid in players}
    for e in events:
        row=result[e['player_id']]
        row['confirmed_events' if e['status']=='confirmed' else 'pending_events']+=1
        for k,v in contributions(e).items():row['metrics'][k]+=v
        if e['status']=='confirmed' and e['kind']=='pass':
            suffix={'complete':'completed','incomplete':'incomplete','unknown':'unknown'}[e['outcome']];row[f'passes_{suffix}']+=1
    return list(result.values())

def validate_assignment(value,players,duration,fragments,existing):
    player=value.get('player_id')
    if player not in players:raise ValueError('Jugador desconocido')
    raw=value.get('track_id');tid=int(number(raw,'ID'))
    if tid!=number(raw,'ID') or tid not in fragments:raise ValueError('Fragmento desconocido')
    start=number(value.get('start'),'Inicio');end=number(value.get('end'),'Fin')
    if not 0<=start<=end<=duration:raise ValueError('Intervalo fuera del vídeo')
    fragment=fragments[tid]
    if not any(r['start']<=end and r['end']>=start for r in fragment['runs']):raise ValueError('El fragmento no aparece en ese intervalo')
    for a in existing:
        if a['end']>=start and a['start']<=end and (a['track_id']==tid or a['player_id']==player):
            raise ValueError('La identidad se solapa con otra asignación. Corrige el intervalo o retira la anterior.')
    note=value.get('note','')
    if not isinstance(note,str) or len(note)>2000:raise ValueError('Nota inválida')
    return {'player_id':player,'track_id':tid,'start':round(start,4),'end':round(end,4),'note':note}
