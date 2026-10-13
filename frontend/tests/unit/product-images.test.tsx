import { createElement, type ReactNode } from 'react';
import { QueryClientProvider } from '@tanstack/react-query';
import { act, cleanup, fireEvent, render, renderHook, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AxiosHeaders, type AxiosResponse } from 'axios';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import ProductImageManager from '../../src/components/products/ProductImageManager';
import OwnerProductImage from '../../src/components/products/OwnerProductImage';
import PublicProductGallery from '../../src/components/products/PublicProductGallery';
import { ownProductImageSchema, ownProductImageListSchema, imageRefSchema, validateUpload } from '../../src/features/productImages/schemas';
import { getOwnerImageBlob, publicImageUrl } from '../../src/features/productImages/api';
import { imageKeys, useImageMutation } from '../../src/features/productImages/hooks';
import * as imageApi from '../../src/features/productImages/api';
import { productKeys } from '../../src/features/products/hooks';
import type { OwnProduct } from '../../src/features/products/types';
import type { OwnProductImage } from '../../src/features/productImages/types';
import { queryClient } from '../../src/app/queryClient';
import { apiClient, clearAuthenticatedSession } from '../../src/services/apiClient';
import { useAuthStore } from '../../src/stores/authStore';

const slug='item-'+'a'.repeat(24);
const ref='img-'+'a'.repeat(32);
const base='/seller/products/'+slug+'/images';
const item: OwnProductImage={ref,position:0,url:'/api/v1'+base+'/'+ref,mime_type:'image/png',
  width:12,height:8,file_size:3,created_at:'2026-10-12T00:00:00Z'};
const product: OwnProduct={public_slug:slug,title:'Study desk',description:'A sturdy desk in good condition.',
  price:'123.45',currency:'CNY',condition:'good',status:'DRAFT',published_at:null,city_active:true,category_active:true,
  city:{slug:'qingdao',name_en:'Qingdao',name_zh:'青岛',province_en:'Shandong',province_zh:'山东',country_code:'CN'},
  category:{slug:'study',name_en:'Study',name_zh:'学习',description:null,parent_slug:null},
  created_at:item.created_at,updated_at:item.created_at};
const wrapper=({children}:{children:ReactNode})=>createElement(QueryClientProvider,{client:queryClient},children);
function response<T>(data:T):AxiosResponse<T>{
  return {data,status:200,statusText:'OK',headers:new AxiosHeaders(),config:{headers:new AxiosHeaders()}};
}
function signIn(id='owner'){
  useAuthStore.getState().setAuthenticated('memory-test-token',{id,email:null,phoneNumber:null,accountStatus:'ACTIVE',
    roles:['BUYER'],emailVerified:true,phoneVerified:true,createdAt:item.created_at});
}
const nativeURL=globalThis.URL;
const createUrl=vi.fn(()=> 'blob:synthetic-private-image');
const revokeUrl=vi.fn();
beforeEach(()=>{
  queryClient.clear();signIn();createUrl.mockClear();revokeUrl.mockClear();
  class TestURL extends nativeURL { static createObjectURL=createUrl; static revokeObjectURL=revokeUrl; }
  vi.stubGlobal('URL',TestURL);
});
afterEach(()=>{cleanup();queryClient.clear();vi.restoreAllMocks();vi.unstubAllGlobals();useAuthStore.getState().setBootstrapping();});
function mockImages(initial:OwnProductImage[]){
  let current=initial;
  vi.spyOn(apiClient,'get').mockImplementation(async(path)=>response(String(path).endsWith('/images')
    ?current:new Blob(['png'],{type:'image/png'})));
  return (images:OwnProductImage[])=>{current=images;};
}

it.each(['id','storage_key','product_listing_id','filename','bucket','path','seller_user_id'])('rejects private metadata field %s',(field)=>{
  expect(ownProductImageSchema.safeParse({...item,[field]:'private'}).success).toBe(false);
});
it.each(['../secret','img-'+'A'.repeat(32),ref+'\n',ref+'?token=private','550e8400-e29b-41d4-a716-446655440000'])('rejects unsafe reference %s',(value)=>{
  expect(imageRefSchema.safeParse(value).success).toBe(false);
});
it.each(['javascript:alert(1)','https://evil.test/x',item.url+'?token=private',item.url+'\n'])('rejects unsafe returned media location %s',(url)=>{
  expect(ownProductImageSchema.safeParse({...item,url}).success).toBe(false);
});
it('requires unique contiguous positions and bounded dimensions/size',()=>{
  expect(ownProductImageListSchema.safeParse([item,{...item,position:1}]).success).toBe(false);
  expect(ownProductImageListSchema.safeParse([{...item,position:1}]).success).toBe(false);
  expect(ownProductImageSchema.safeParse({...item,width:6000,height:6000}).success).toBe(false);
  expect(ownProductImageSchema.safeParse({...item,file_size:10*1024*1024+1}).success).toBe(false);
});
it('validates file type/actual size for UX without trusting filename',()=>{
  expect(validateUpload(new File(['x'],'../../secret.exe',{type:'image/png'}))).toBeNull();
  expect(validateUpload(new File(['x'],'fake.jpg',{type:'image/svg+xml'}))).toMatch(/JPEG/);
  expect(validateUpload(new File([],'empty.png',{type:'image/png'}))).toMatch(/1 byte/);
});
it('constructs public URLs from configured API location and public refs, never returned paths',()=>{
  const previous=apiClient.defaults.baseURL;
  try{
    apiClient.defaults.baseURL='https://api.example.test/api/v1';
    expect(publicImageUrl(slug,ref)).toBe('https://api.example.test/api/v1/products/'+slug+'/images/'+ref);
    apiClient.defaults.baseURL='https://api.example.test/api/v1?token=private';
    expect(()=>publicImageUrl(slug,ref)).toThrow();
    expect(()=>publicImageUrl('../secret',ref)).toThrow();
  }finally{apiClient.defaults.baseURL=previous;}
});
it('owner preview uses authenticated blob requests and revokes URL on unmount',async()=>{
  mockImages([item]);
  const view=render(<OwnerProductImage slug={slug} imageRef={ref} position={0}/>,{wrapper});
  const image=await screen.findByRole('img',{name:'Your product image 1'});
  await waitFor(()=>expect(image).toHaveAttribute('src','blob:synthetic-private-image'));
  expect(apiClient.get).toHaveBeenCalledWith(base+'/'+ref,{responseType:'blob'});
  view.unmount();
  expect(revokeUrl).toHaveBeenCalledWith('blob:synthetic-private-image');
});
it('logout removes visible private preview and revokes its object URL immediately',async()=>{
  mockImages([item]);
  render(<OwnerProductImage slug={slug} imageRef={ref} position={0}/>,{wrapper});
  await screen.findByRole('img');
  await waitFor(()=>expect(createUrl).toHaveBeenCalled());
  await act(async()=>clearAuthenticatedSession());
  expect(screen.queryByRole('img')).toBeNull();
  expect(revokeUrl).toHaveBeenCalledWith('blob:synthetic-private-image');
});
it('account switch never renders the previous owner blob',async()=>{
  mockImages([item]);
  render(<OwnerProductImage slug={slug} imageRef={ref} position={0}/>,{wrapper});
  await waitFor(()=>expect(createUrl).toHaveBeenCalledTimes(1));
  vi.spyOn(apiClient,'get').mockImplementation(()=>new Promise(()=>{}));
  await act(async()=>signIn('second-owner'));
  expect(screen.queryByRole('img')).toBeNull();
  expect(revokeUrl).toHaveBeenCalledWith('blob:synthetic-private-image');
});
it('late blob response is rejected after logout before creating any object URL',async()=>{
  let resolve!:(response:AxiosResponse<Blob>)=>void;
  vi.spyOn(apiClient,'get').mockReturnValue(new Promise<AxiosResponse<Blob>>((done)=>{resolve=done;}));
  const pending=getOwnerImageBlob(slug,ref);
  const rejected=expect(pending).rejects.toThrow('Session changed.');
  clearAuthenticatedSession();
  resolve(response(new Blob(['png'],{type:'image/png'})));
  await rejected;
  expect(createUrl).not.toHaveBeenCalled();
});
it('blob failures/invalid content type show a safe fallback',async()=>{
  vi.spyOn(apiClient,'get').mockResolvedValue(response(new Blob(['PRIVATE DRIVER ERROR'],{type:'text/html'})));
  render(<OwnerProductImage slug={slug} imageRef={ref} position={0}/>,{wrapper});
  expect(await screen.findByText('Preview unavailable.')).toBeInTheDocument();
  expect(screen.queryByText('PRIVATE DRIVER ERROR')).toBeNull();
  expect(createUrl).not.toHaveBeenCalled();
});
it('rapid upload actions issue only one multipart request and omit personal filename',async()=>{
  mockImages([]);
  let resolve!:(response:AxiosResponse<OwnProductImage>)=>void;
  const post=vi.spyOn(apiClient,'post').mockReturnValue(new Promise<AxiosResponse<OwnProductImage>>((done)=>{resolve=done;}));
  const user=userEvent.setup();
  render(<ProductImageManager product={product}/>,{wrapper});
  await screen.findByText(/No images yet/);
  await user.upload(screen.getByLabelText('Add image'),new File(['png'],'PRIVATE PERSONAL NAME.png',{type:'image/png'}));
  await act(async()=>{
    fireEvent.click(screen.getByRole('button',{name:'Upload image'}));
    fireEvent.click(screen.getByRole('button',{name:'Upload image'}));
  });
  await waitFor(()=>expect(post).toHaveBeenCalledTimes(1));
  const [,form,config]=post.mock.calls[0];
  expect(form).toBeInstanceOf(FormData);
  if(!(form instanceof FormData))throw new Error('Expected multipart');
  const part=form.get('file');
  expect(part).toBeInstanceOf(File);
  if(!(part instanceof File))throw new Error('Expected file');
  expect(part.name).toBe('product-image');
  expect(config?.headers).toEqual({'Content-Type':undefined});
  await act(async()=>{resolve(response(item));});
});
it('reorder sends the whole ref set and delete removes/resequences current metadata',async()=>{
  const second={...item,ref:'img-'+'b'.repeat(32),position:1,url:'/api/v1'+base+'/img-'+'b'.repeat(32)};
  const setImages=mockImages([item,second]);
  const patch=vi.spyOn(apiClient,'patch').mockImplementation(async()=>{
    const ordered=[{...second,position:0},{...item,position:1}];setImages(ordered);return response(ordered);
  });
  const remove=vi.spyOn(apiClient,'delete').mockImplementation(async()=>{setImages([{...item,position:0}]);return response(undefined);});
  const user=userEvent.setup();
  render(<ProductImageManager product={product}/>,{wrapper});
  await screen.findByText('Cover image');
  await user.click(screen.getAllByRole('button',{name:'Move right'})[0]);
  await waitFor(()=>expect(patch).toHaveBeenCalledWith(base+'/order',{images:[second.ref,ref]}));
  await user.click(await screen.findByRole('button',{name:'Delete image 1'}));
  await waitFor(()=>expect(remove).toHaveBeenCalledWith(base+'/'+second.ref));
  await waitFor(()=>expect(screen.queryByRole('button',{name:'Delete image 2'})).toBeNull());
});
it('archived management allows deletion but never upload or reorder',async()=>{
  mockImages([item]);
  render(<ProductImageManager product={{...product,status:'ARCHIVED'}}/>,{wrapper});
  await screen.findByText('Cover image');
  expect(screen.queryByLabelText('Add image')).toBeNull();
  expect(screen.queryByRole('button',{name:'Move right'})).toBeNull();
  expect(screen.getByRole('button',{name:'Delete image 1'})).toBeEnabled();
});
it('public gallery handles zero images and byte-read failure without private details',()=>{
  const view=render(<PublicProductGallery slug={slug} images={[]}/>);
  expect(screen.getByText('No product images.')).toBeInTheDocument();
  view.rerender(<PublicProductGallery slug={slug} images={[{ref,position:0,url:'/api/v1/products/'+slug+'/images/'+ref}]}/>);
  const image=screen.getByRole('img',{name:'Product cover image'});
  expect(image.getAttribute('src')).not.toContain('token=');
  fireEvent.error(image);
  expect(screen.getByText('Image unavailable.')).toBeInTheDocument();
});
it('private image metadata and blobs are removed by session clearing',async()=>{
  const version=useAuthStore.getState().sessionVersion;
  await queryClient.fetchQuery({queryKey:imageKeys.mine('owner',version,slug),meta:{private:true},queryFn:async()=>[item]});
  await queryClient.fetchQuery({queryKey:imageKeys.blob('owner',version,slug,ref),meta:{private:true},queryFn:async()=>new Blob(['png'])});
  clearAuthenticatedSession();
  expect(queryClient.getQueryData(imageKeys.mine('owner',version,slug))).toBeUndefined();
  expect(queryClient.getQueryData(imageKeys.blob('owner',version,slug,ref))).toBeUndefined();
});
it('media mutation does not invalidate unsaved product information and cannot write old-session caches',async()=>{
  const version=useAuthStore.getState().sessionVersion;
  const own=productKeys.own('owner',version,slug);
  queryClient.setQueryData(own,product);
  vi.spyOn(imageApi,'uploadProductImage').mockResolvedValue(item);
  const {result}=renderHook(()=>useImageMutation(slug),{wrapper});
  await act(async()=>{await result.current.mutateAsync({action:'upload',file:new File(['x'],'x.png',{type:'image/png'})});});
  expect(queryClient.getQueryState(own)?.isInvalidated).toBe(false);
  let finish!:(image:OwnProductImage)=>void;
  vi.spyOn(imageApi,'uploadProductImage').mockReturnValue(new Promise<OwnProductImage>((done)=>{finish=done;}));
  let pending!:Promise<unknown>;
  await act(async()=>{pending=result.current.mutateAsync({action:'upload',file:new File(['x'],'x.png',{type:'image/png'})});await Promise.resolve();});
  clearAuthenticatedSession();signIn('other');
  await act(async()=>{finish(item);await pending;});
  expect(queryClient.getQueryData(own)).toBeUndefined();
});
