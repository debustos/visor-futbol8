"""Standalone top-down density images, excluding unobserved and unprojected intervals."""
from pathlib import Path
import os,json,numpy as np
from runtime_context import ROOT,WORK,CACHE,SOURCE
os.environ['MPLCONFIGDIR']=str(WORK/'matplotlib-cache')
from scipy.ndimage import gaussian_filter
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle,Circle
def main():
    profiles=json.loads((ROOT/'automatic/profiles.json').read_text());dest=ROOT/'mapas';dest.mkdir(exist_ok=True)
    for p in profiles:
        fig,ax=plt.subplots(figsize=(5.2,7.8),dpi=160);fig.set_facecolor('#111417');ax.set_facecolor('#174435');ax.set_xlim(-5,105);ax.set_ylim(108,-8);ax.set_aspect(.64)
        for i in range(10):ax.add_patch(Rectangle((0,i*10),100,10,facecolor='#1c4b3c' if i%2 else '#174435',zorder=0))
        pts=p['heatmap_points'];grid=np.zeros((90,64))
        for q in pts:grid[min(89,round(q['y']*.89)),min(63,round(q['x']*.63))]+=q.get('weight_seconds',.2)
        grid=gaussian_filter(grid,2.2)
        if grid.max():
            relative=grid/grid.max();ax.imshow(np.ma.masked_less(relative,.02),extent=[0,100,100,0],cmap='inferno',alpha=.8,interpolation='bilinear',zorder=1,vmin=0,vmax=1)
        else:ax.text(50,50,'Sin posiciones identificadas',ha='center',va='center',color='white',fontsize=12)
        for rect in [(0,0,100,100),(25,0,50,17),(25,83,50,17),(42.5,-2,15,2),(42.5,100,15,2)]:ax.add_patch(Rectangle(rect[:2],*rect[2:],fill=False,edgecolor='#e7f5eb',linewidth=1,zorder=2))
        ax.plot([0,100],[50,50],color='#e7f5eb',lw=1,zorder=2);ax.add_patch(Circle((50,50),10,fill=False,edgecolor='#e7f5eb',lw=1,zorder=2));ax.text(50,-5,'PORTERÍA RIVAL',ha='center',color='#e7f5eb',fontsize=8);ax.text(50,106,'PORTERÍA PROPIA',ha='center',color='#e7f5eb',fontsize=8);ax.axis('off')
        ax.set_title(f"#{p['jersey_number']} · {p['nickname'].capitalize()}",color='#ff9a48',fontsize=17,pad=15)
        fig.text(.5,.044,f"{len(pts):,} posiciones · {p.get('mapped_seconds',p['visible_seconds'])} s proyectados · {p.get('mapped_coverage_percent',p['coverage_percent'])}% grabación".replace(',','.'),ha='center',color='#e7f5eb',fontsize=9)
        fig.text(.5,.022,'Primera parte · geometría aproximada · densidad relativa del jugador',ha='center',color='#aeb6c1',fontsize=7)
        fig.subplots_adjust(top=.92,bottom=.09,left=.1,right=.9);fig.savefig(dest/f"{p['jersey_number']}-{p['nickname'].lower()}.png",facecolor=fig.get_facecolor());plt.close(fig)
    print('Exported',len(profiles),'heatmaps (unknown players explicitly empty)')
if __name__=='__main__':main()
