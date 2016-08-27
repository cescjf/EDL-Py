import numpy as np
from EntryEquations import Entry
from Triggers import DeployParachute, findTriggerPoint
from Target import Target
from scipy.integrate import odeint
from Utils.redirect import stdout_redirected
from functools import partial

def HEPBankReduced(T,t1,t2,minBank = np.radians(15.), maxBank = np.radians(85.)):
    maxRate = np.radians(20.)
    ti1 = t1 + 2*(maxBank)/maxRate
    ti2 = t2 + (maxBank+minBank)/maxRate
    isScalar = False
    bank = []
    if isinstance(T,(float,int,np.float32,np.float64)):
        T = [T]
        isScalar = True

    for t in T:

        if t <= t1:
            bank.append(maxBank)
        elif t >= t1 and t <= ti1:
            bank.append(maxBank-maxRate*(t-t1))
        elif t >= ti1 and t <= t2:
            bank.append(-maxBank)
        elif t >= t2 and t <= ti2:
            bank.append(-maxBank + maxRate*(t-t2))
        else:
            bank.append(minBank)
    if isScalar:
        try:
            return bank[0]
        except:
            print "Bank angle comp failed"
            return -1.
    else:
        return bank

        
def HEPBankReducedSmooth(T,t1,t2,minBank = np.radians(15.), maxBank = np.radians(85.)):
    maxRate = np.radians(20)
    maxAcc = np.radians(5)
    dt = maxRate/maxAcc                                     # Amount of time to go from 0 bank rate to max or vice versa
    dbank = 0.5*(maxRate**2)/maxAcc                         # Angle traversed during max accel for dt seconds
    t1a = t1+dt                                             # Acceleration phase
    t1v = t1 + 2*maxBank/maxRate                            # Max velocity phase
    t1d = t1v + dt                                          # Max deceleration phase    #Future: check that this is less than t2
    if t1d >= t2:
        noMax1 = True
    else:
        noMax1 = False
    
    t2a = t2 + dt
    t2v = t2 + (minBank+maxBank)/maxRate
    t2d = t2v + dt
    
    isScalar = False
    bank = []
    if isinstance(T,(float,int,np.float32,np.float64)):
        T = [T]
        isScalar = True
        
    for t in T:
        if t <= t1:
            bank.append(maxBank)
        elif t > t1 and t <= t1a: #Negative acceleration phase
            bank.append(maxBank-0.5*maxAcc*(t-t1)**2)
        elif t > t1a and t <= t1v: #Max velocity phase
            bank.append(maxBank-dbank-maxRate*(t-t1a))
        elif t > t1v and t <= t1d:
            bank.append(dbank-maxBank - maxRate*(t-t1v) + 0.5*maxAcc*(t-t1v)**2 )
        elif t > t1d and t <= t2:
            bank.append(-maxBank)
        elif t > t2 and t <= t2a:
            bank.append(-maxBank + 0.5*maxAcc*(t-t2)**2)
        elif t > t2a and t <= t2v:
            bank.append(dbank-maxBank + maxRate*(t-t2a))
        elif t > t2v and t <= t2d:
            bank.append(minBank-dbank + maxRate*(t-t2v) - 0.5*maxAcc*(t-t2v)**2)
        else:
            bank.append(minBank)
        
    return bank
        
def HEPBank(T,t1,t2,t3,minBank = np.radians(15.), maxBank = np.radians(85.)):

    maxRate = np.radians(20.)
    ti1 = t1 + (maxBank+minBank)/maxRate
    ti2 = t2 + 2*(maxBank)/maxRate
    ti3 = t3 + (maxBank+minBank)/maxRate
    isScalar = False
    bank = []
    if isinstance(T,(float,int,np.float32,np.float64)):
        T = [T]
        isScalar = True

    for t in T:
        if t < t1 and t >= 0:
            bank.append(-minBank) 
        elif t >= t1 and t <= ti1:
            bank.append(-minBank+maxRate*(t-t1))
        elif t >= ti1 and t <= t2:
            bank.append(maxBank)
        elif t >= t2 and t <= ti2:
            bank.append(maxBank-maxRate*(t-t2))
        elif t >= ti2 and t <= t3:
            bank.append(-maxBank)
        elif t >= t3 and t <= ti3:
            bank.append(-maxBank + maxRate*(t-t3))
        else:
            bank.append(minBank)
    if isScalar:
        try:
            return bank[0]
        except:
            print "Bank angle comp failed"
            return -1.
    else:
        return bank

def checkFeasibility(T,sign=-1):
    
    sig = sign*np.diff(T) #np.array([T[0]-T[1],T[1]-T[2]])
    cost = (sum(sig+np.abs(sig)) + sum(abs(T)-T))*1e5
    if cost:
        return max(cost,1e7)
    else:
        return 0
        
def HEPCost(T, x0, entry = Entry(Trigger = partial(DeployParachute,{'velBias':30})), target = Target(), bank = HEPBank, getIV = (lambda x,t: t), check=checkFeasibility):
    
    J = check(T)
    if J > 300:
        return J
        
    hep = lambda x,t: bank(getIV(x,t),*T)

        
    time = np.linspace(0,450,1000)


    with stdout_redirected():
        X = odeint(entry.dynamics(hep), x0, time)


    idx = findTriggerPoint(X,time)-1
    h     = entry.altitude(X[idx,0], km=True)
    dr,cr = entry.planet.range(*x0[[1,2,5]], lonc = X[idx,1], latc = X[idx,2],km=True)

    Wh = 0.8*1e-6
    J = -h*Wh + ((target.DR-dr)**2 + (target.CR-cr)**2)**0.5

    return J

    
def Optimize(x0,n=3,iv='time'):
    
    from scipy.optimize import minimize, minimize_scalar
       
    if (n == 3):
        guess = [50,100,133]
        bankFun = HEPBank
    elif (n==2):
        guess = [106,133]
        bankFun = HEPBankReducedSmooth
    else:   
        print "Optimize: improper input for n."
        return None
    
    if iv.lower() == 'time':
        getIV = lambda x,t: t
        check = checkFeasibility
        
    elif 'vel' in iv.lower():
        if n == 2:
            guess = [-4700,-2100]
        elif n == 3:
            guess = [-5100,-4500,-2500]
        getIV = lambda x,t: -x[3]
        check = lambda v: checkFeasibility(-v,sign=1)
    
    entry = Entry(Trigger = partial(DeployParachute,{'velBias':30}))
    sol = minimize(HEPCost,np.array(guess),args = (x0, entry, Target(), bankFun, getIV, check), method='Nelder-Mead',tol=1e-5,options={'disp':True})
    # sol = minimize(HEPCost,np.array(guess),args = (x0, entry, Target(), bankFun, getIV, check), method='Powell',tol=1e-5,options={'disp':True})
    print "The {0} switching {1}s are {2}".format(n,iv,sol.x)
    return (lambda x,t: bankFun(getIV(x,t),*sol.x)), sol.x

def OptimizeSmooth(x0):
    from scipy.optimize import minimize, differential_evolution
    
    entry = Entry(Trigger=partial(DeployParachute,{'velBias':30}))
    bankFun = HEPBankReducedSmooth
    # bankFun = HEPBank

    # guess = [108,133]
    getIV = lambda x,t: t
    check = lambda T: True
    
    
    bounds = [(0,250),(100,350)]
    # bounds = [(0,250),(0,250),(100,350)]
    # constraints = [{'type':'ineq','fun': (lambda T:T[1]-T[0]-12) },{'type':'ineq','fun': (lambda T:T[0]) }]
    
    # sol = minimize(HEPCost,np.array(guess),args = (x0, entry, Target(), bankFun, getIV, check),bounds=bounds, method='SLSQP', constraints=constraints, tol=1e-5,options={'disp':True}) # SLSQP
    # sol = minimize(HEPCost,np.array(guess),args = (x0, entry, Target(), bankFun, getIV, check), method='COBYLA', constraints=constraints, tol=1e-5,options={'disp':True}) #COBYLA doesn't handle bounds
    sol = differential_evolution(HEPCost,args = (x0, entry, Target(), bankFun, getIV, check),bounds=bounds, tol=1e-1, disp=True)

    print "The 2 switching times are {} with final cost {}".format(sol.x,sol.fun)

    return (lambda x,t: bankFun(getIV(x,t),*sol.x)), sol

   

def ExpandBank():
    import chaospy as cp
    
    hep = HEPBankReducedSmooth
    
    t = np.linspace(0,350,3500)
    t1 = cp.Uniform(0,150)
    t2 = cp.Uniform(100, 260)
    
    t1 = cp.Normal(70,1)
    t2 = cp.Normal(115,1)
    pdf = cp.J(t1,t2)
    polynomials = cp.orth_ttr(order=2, dist=pdf) #No good for dependent
    # polynomials = cp.orth_bert(N=2,dist=pdf) 
    # polynomials = cp.orth_gs(order=2,dist=pdf) 
    # polynomials = cp.orth_chol(order=2,dist=pdf) 
    
    if 1:
        nodes, weights = cp.generate_quadrature(order=2, domain=pdf, rule="Gaussian")
        # nodes, weights = cp.generate_quadrature(order=2, domain=pdf, rule="C")
        # nodes, weights = cp.generate_quadrature(order=9, domain=pdf, rule="L")
        print nodes.shape
        samples = np.array([hep(t,*node) for node in nodes.T])
        hepPCE = cp.fit_quadrature(polynomials,nodes,weights,samples)
    else:
        nodes = pdf.sample(10,'S')
        samples = np.array([hep(t,*node) for node in nodes.T])
        hepPCE = cp.fit_regression(polynomials, nodes, samples,rule='T')
    return hepPCE


def testExpansion():
    '''
    Conclusions from running this over and over with different inputs:
        Order is very important. This problem works best by far with order 2
        Polynomial type had very little impact
        Quadrature performed best with Gaussian, order must match
        Collocation worked best with T(ikhonov Regularization), and had similar performance with quadrature for a similar number of evaluations

    '''
    import matplotlib.pyplot as plt
    model = ExpandBank()
    hep = lambda t: HEPBankReducedSmooth(t,71,113)

    t = np.linspace(0,350,3500)
    ti = np.linspace(0,350,3500)
    test = model(*[71,113])
    
    plt.plot(ti,hep(ti))  
    plt.plot(t,test)
    plt.show()

if __name__ == '__main__':
    testExpansion()
    
    