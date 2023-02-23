#include<bits/stdc++.h>

using namespace std;

typedef unsigned char uchar;

template<typename T1, typename T2>
double calc_distance(T1* a, T2* b, int len){
    double distance=0;
    for(int i=0;i<len;i++){
        distance += pow(int(*a)-int(*b), 2);
        a++, b++;
    }
    return sqrt(distance);
}

template<typename T1, typename T2>
double calc_distance(vector<T1> a, const T2* b, int len){
    return calc_distance(&a[0], b, len);
}

template<typename T1, typename T2>
double calc_distance(vector<T1> a, vector<T2> b, int len){
    return calc_distance(&a[0], &b[0], len);
}

template<typename T1,typename T2>
double calc_distance(T1 a,const vector<T2> &b, int len){
    return calc_distance(a, &b[0], len);
}
